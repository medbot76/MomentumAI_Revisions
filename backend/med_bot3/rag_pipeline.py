"""Med-Bot AI — Gemini + Local PostgreSQL Retrieval-Augmented Generation engine
-------------------------------------------------------------------------------
Self-contained class that handles PDF ingestion, chunking, vector
storage, retrieval, and answer generation — powered by Google Gemini
models with local PostgreSQL for vector storage.

Migrated from Supabase to use local PostgreSQL database with SQLAlchemy.
Embeddings stored as JSON arrays with Python-based cosine similarity.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
import logging
from io import BytesIO
from typing import List, TypedDict, Union
from PIL import Image, ImageStat

import fitz
import numpy as np
import tiktoken
from pydantic import BaseModel
import google.generativeai as genai
import json

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False
    print("Warning: pytesseract not available (OCR disabled)")

try:
    import torch
    from transformers import BlipProcessor, BlipForConditionalGeneration
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    print("Warning: torch/transformers not available (BLIP model disabled)")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None
    print("Warning: sentence_transformers not available (local embeddings disabled)")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

ENCODER = tiktoken.get_encoding("cl100k_base")

BLIP_AVAILABLE = False
processor = None
model = None
device = None
if TORCH_AVAILABLE:
    try:
        processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        BLIP_AVAILABLE = True
    except Exception as e:
        print(f"Warning: BLIP model initialization failed: {str(e)}")


class ChunkData(BaseModel):
    id: str
    text: str
    tokens: int
    metadata: dict


class QueryResult(TypedDict):
    answer: str
    chunks: List[ChunkData]


def _token_count(text: str) -> int:
    return len(ENCODER.encode(text))


_sentence_model = None

def _get_sentence_model():
    global _sentence_model
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        raise ImportError("sentence_transformers not available. Using API embeddings instead.")
    if _sentence_model is None:
        _sentence_model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    return _sentence_model


def _l2_normalize(x: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    if x.ndim == 1:
        denom = max(np.linalg.norm(x), eps)
        return (x / denom).astype(np.float32)
    denom = np.linalg.norm(x, axis=1, keepdims=True)
    denom = np.maximum(denom, eps)
    return (x / denom).astype(np.float32)


def _embed_text_api(text: str) -> List[float]:
    try:
        import requests
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={api_key}"
        payload = {
            "model": "models/text-embedding-004",
            "content": {
                "parts": [{"text": text}]
            }
        }
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        embedding = result.get("embedding", {}).get("values", [])
        
        if not embedding:
            raise ValueError("No embedding returned from API")
        
        if len(embedding) < 768:
            embedding = embedding + [0.0] * (768 - len(embedding))
        elif len(embedding) > 768:
            embedding = embedding[:768]
        
        embedding = np.array(embedding, dtype=np.float32)
        embedding = _l2_normalize(embedding)
        return embedding.tolist()
    except Exception as e:
        logging.warning(f"API embedding failed: {e}. Using simple hash-based embedding as last resort.")
        import hashlib
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()
        repeated_bytes = (hash_bytes * (768 // 32 + 1))[:768]
        embedding = np.array(list(repeated_bytes), dtype=np.float32)
        embedding = embedding / 255.0
        embedding = _l2_normalize(embedding)
        return embedding.tolist()


def _embed_texts_api(texts: List[str]) -> np.ndarray:
    embeddings = []
    for text in texts:
        embeddings.append(_embed_text_api(text))
    return _l2_normalize(np.array(embeddings, dtype=np.float32))


def _embed_text(text: str) -> List[float]:
    if SENTENCE_TRANSFORMERS_AVAILABLE:
        try:
            model = _get_sentence_model()
            embedding = model.encode(text, convert_to_numpy=True, normalize_embeddings=False)
            embedding = _l2_normalize(embedding)
            return embedding.tolist()
        except Exception as e:
            logging.warning(f"Local embedding failed: {e}. Falling back to API embeddings.")
            return _embed_text_api(text)
    else:
        return _embed_text_api(text)


def _embed_texts(texts: List[str]) -> np.ndarray:
    if SENTENCE_TRANSFORMERS_AVAILABLE:
        try:
            model = _get_sentence_model()
            embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=False)
            return _l2_normalize(embeddings)
        except Exception as e:
            logging.warning(f"Local embeddings failed: {e}. Falling back to API embeddings.")
            return _embed_texts_api(texts)
    else:
        return _embed_texts_api(texts)


class RAGPipeline:
    """Gemini + Local PostgreSQL Retrieval-Augmented Generation engine."""

    def __init__(
        self,
        *,
        max_tokens_per_chunk: int = 500,
        similarity_threshold: float = 0.30,
        db_session=None,
        app=None
    ):
        self.max_tokens = max_tokens_per_chunk
        self.similarity_threshold = similarity_threshold
        self.gemini_vision = genai.GenerativeModel('gemini-2.0-flash')
        self.logger = logging.getLogger(__name__)
        self._db_session = db_session
        self._app = app
        
    def set_app_context(self, app, db_session):
        self._app = app
        self._db_session = db_session

    def _get_db(self):
        from models import db
        return db
    
    def _get_chunk_model(self):
        from models import Chunk
        return Chunk
    
    def _get_notebook_model(self):
        from models import Notebook
        return Notebook

    def contains_text(self, image: Image.Image) -> bool:
        if not PYTESSERACT_AVAILABLE:
            return False
        try:
            gray_image = image.convert('L')
            data = pytesseract.image_to_data(gray_image, output_type=pytesseract.Output.DICT)

            for i, conf_str in enumerate(data['conf']):
                try:
                    conf = int(conf_str)
                    text = data['text'][i].strip()
                    if conf > 50 and text:
                        return True
                except ValueError:
                    continue
            return False
        except Exception as e:
            print(f"Error in OCR processing: {str(e)}")
            return False
        
    def _is_valid_image(self, image: Image.Image) -> bool:
        try:
            min_width, min_height = 100, 100
            if image.width < min_width or image.height < min_height:
                return False
            
            stat = ImageStat.Stat(image.convert("L"))
            if stat.stddev[0] < 5:
                return False
            
            if image.width < 150 and image.height < 150:
                return self.contains_text(image)
            return True
        except Exception as e:
            print(f"Error validating image: {str(e)}")
            return False

    async def analyze_image(self, image: Union[Image.Image, bytes], *, notebook_id: str = "default", user_id: str = None, document_id: str = None) -> None:
        try:
            if isinstance(image, bytes): 
                image = Image.open(BytesIO(image))
                
            if not self._is_valid_image(image):
                raise ValueError("Image is not suitable for analysis.")
            
            if image.mode == 'RGBA': 
                image = image.convert('RGB')
            
            try:
                response = await asyncio.to_thread(
                    self.gemini_vision.generate_content,
                    [
                        "Analyze this image and provide a detailed description of its content, "
                        "focusing on any diagrams, charts, or relevant visual information. ",
                        image  
                    ]
                )
                description = response.text
                print("Successfully analyzed image using Gemini Vision")
            except Exception as gemini_error:
                print(f"Gemini Vision analysis failed: {str(gemini_error)}")
                if not BLIP_AVAILABLE:
                    raise Exception("Both Gemini Vision and BLIP are unavailable")
                
                description = self._generate_blip_caption(image)
                print("Successfully analyzed image using BLIP")
            
            chunk_data = ChunkData(
                id=str(uuid.uuid4()),
                text=description,
                tokens=_token_count(description),
                metadata={
                    "notebook_id": notebook_id,
                    "type": "image",
                    "timestamp": str(uuid.uuid4()),
                    "analyzer": "gemini" if "gemini_error" not in locals() else "blip"
                }
            )
            await self._store_chunks([chunk_data], user_id, notebook_id, document_id)
        except Exception as e:
            raise Exception(f"Error analyzing image: {str(e)}")

    def _generate_blip_caption(self, image: Image.Image) -> str:
        try:
            inputs = processor(images=image, return_tensors="pt").to(device)
            output = model.generate(**inputs)
            caption = processor.decode(output[0], skip_special_tokens=True)
            
            enhanced_caption = (
                f"This image shows: {caption}. "
                "The image appears to be a diagram or illustration that may contain "
                "important visual information relevant to the document's content."
            )
            return enhanced_caption
        except Exception as e:
            raise Exception(f"Error generating BLIP caption: {str(e)}")

    async def ingest_txt(self, text: Union[str, bytes], *, notebook_id: str = "default", user_id: str = None, document_id: str = None) -> None:
        if isinstance(text, bytes):
            text = text.decode('utf-8')

        chunks: list[ChunkData] = []
        buffer = ""
        
        sentences = text.replace('\n', ' ').split('. ')
        for sentence in sentences:
            buffer += sentence + '. '
            if _token_count(buffer) >= self.max_tokens:
                chunks.append(
                    ChunkData(
                        id=str(uuid.uuid4()),
                        text=buffer.strip(),
                        tokens=_token_count(buffer),
                        metadata={"notebook_id": notebook_id, "type": "text"},
                    )
                )
                buffer = ""
        if buffer:
            chunks.append(
                ChunkData(
                    id=str(uuid.uuid4()),
                    text=buffer.strip(),
                    tokens=_token_count(buffer),
                    metadata={"notebook_id": notebook_id, "type": "text"},
                )
            )
        
        await self._store_chunks(chunks, user_id, notebook_id, document_id)

    async def _store_chunks(self, chunks: List[ChunkData], user_id: str, notebook_id: str = None, document_id: str = None) -> None:
        if not chunks:
            return
            
        embeddings = _embed_texts([c.text for c in chunks])
        
        try:
            from app import app
            from models import db, Chunk as ChunkModel
            
            with app.app_context():
                for i, chunk in enumerate(chunks):
                    nb_id = notebook_id if notebook_id and notebook_id != "default" else None
                    
                    new_chunk = ChunkModel(
                        id=chunk.id,
                        user_id=user_id,
                        notebook_id=nb_id,
                        document_id=document_id,
                        content=chunk.text,
                        tokens=chunk.tokens,
                        embedding=embeddings[i].tolist(),
                        chunk_metadata=chunk.metadata
                    )
                    db.session.add(new_chunk)
                
                db.session.commit()
                self.logger.info(f"Successfully stored {len(chunks)} chunks in local database")
        except Exception as e:
            self.logger.error(f"Failed to store chunks: {e}")
            raise

    async def ingest_pdf(self, pdf: Union[str, bytes], *, notebook_id: str = "default", user_id: str = None, document_id: str = None) -> None:
        if isinstance(pdf, str):
            doc = fitz.open(pdf)
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf)
                doc = fitz.open(tmp.name)

        chunks: list[ChunkData] = []
        buffer = ""

        for page_num, page in enumerate(doc):
            text = page.get_text()
            print(f"Processing PDF page {page_num + 1}/{len(doc)}")
            
            sentences = text.replace('\n', ' ').split('. ')
            for sentence in sentences:
                buffer += sentence + '. '
                if _token_count(buffer) >= self.max_tokens:
                    chunks.append(
                        ChunkData(
                            id=str(uuid.uuid4()),
                            text=buffer.strip(),
                            tokens=_token_count(buffer),
                            metadata={
                                "notebook_id": notebook_id,
                                "type": "pdf",
                                "page": page_num + 1
                            },
                        )
                    )
                    buffer = ""

            images = page.get_images(full=True)
            for img_index, img in enumerate(images):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    pil_image = Image.open(BytesIO(image_bytes))
                    
                    if self._is_valid_image(pil_image):
                        await self.analyze_image(pil_image, notebook_id=notebook_id, user_id=user_id, document_id=document_id)
                except Exception as e:
                    self.logger.warning(f"Failed to process image {img_index} on page {page_num + 1}: {e}")

        if buffer:
            chunks.append(
                ChunkData(
                    id=str(uuid.uuid4()),
                    text=buffer.strip(),
                    tokens=_token_count(buffer),
                    metadata={
                        "notebook_id": notebook_id,
                        "type": "pdf",
                        "page": len(doc)
                    },
                )
            )

        doc.close()
        await self._store_chunks(chunks, user_id, notebook_id, document_id)

    async def ingest_docx(self, docx_file: Union[str, bytes], *, notebook_id: str = "default", user_id: str = None, document_id: str = None) -> None:
        try:
            import docx2txt
            
            if isinstance(docx_file, bytes):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                    tmp.write(docx_file)
                    text = docx2txt.process(tmp.name)
            else:
                text = docx2txt.process(docx_file)
            
            await self.ingest_txt(text, notebook_id=notebook_id, user_id=user_id, document_id=document_id)
        except Exception as e:
            self.logger.error(f"Failed to process DOCX: {e}")
            raise

    async def query(self, question: str, *, notebook_id: str = "default", top_k: int = 5, user_id: str = None) -> QueryResult:
        print(f"\n🔍 Processing query: '{question}'")
        
        q_embed = _embed_text(question)
        
        context = await self._query_local_db(q_embed, notebook_id, top_k, user_id)
        
        if not context:
            print("No chunks passed similarity threshold!")
            return {"answer": "I couldn't find relevant material in your documents.", "chunks": []}
        
        print(f"\nUsing {len(context)} relevant chunks for answer generation")
        
        chunks = [
            ChunkData(id=str(i), text=t, tokens=_token_count(t), metadata=m)
            for t, m, i in context
        ]
        
        context_text = "\n\n".join([chunk.text for chunk in chunks])
        
        prompt = f"""
Based on the following context, please answer the question. If the context doesn't contain enough information to answer the question, say so.

Context:
{context_text}

Question: {question}

Answer:"""
        
        try:
            gen_model = genai.GenerativeModel('gemini-2.0-flash')
            response = gen_model.generate_content(prompt)
            answer = response.text
        except Exception as e:
            self.logger.error(f"Failed to generate answer with Gemini: {e}")
            answer = "I apologize, but I encountered an error while generating the answer."
        
        return {"answer": answer, "chunks": chunks}

    async def _query_local_db(self, q_embed: List[float], notebook_id: str, top_k: int, user_id: str) -> List[tuple[str, dict, str]]:
        try:
            from app import app
            from models import db, Chunk as ChunkModel, Notebook
            
            with app.app_context():
                query = ChunkModel.query.filter_by(user_id=user_id)
                
                if notebook_id and notebook_id != "default":
                    query = query.filter_by(notebook_id=notebook_id)
                elif notebook_id == "default":
                    default_nb = Notebook.query.filter_by(user_id=user_id, name="Default Notebook").first()
                    if default_nb:
                        query = query.filter_by(notebook_id=default_nb.id)
                
                query = query.filter(ChunkModel.embedding.isnot(None))
                results = query.all()
                
                if not results:
                    print("No chunks found in database")
                    return []
                
                documents = [r.content for r in results]
                metadatas = [r.chunk_metadata or {} for r in results]
                ids = [r.id for r in results]
                stored_embeddings = [r.embedding for r in results]
                
                return self._find_relevant_chunks(q_embed, documents, metadatas, ids, stored_embeddings)
                
        except Exception as e:
            self.logger.error(f"Local database query failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _find_relevant_chunks(self, query_embedding: List[float], documents: List[str], 
                    metadatas: List[dict], ids: List[str], stored_embeddings: List[List[float]] = None) -> List[tuple[str, dict, str]]:
        
        relevant_chunks = []
        print(f"\nCalculating similarity scores for {len(documents)} chunks...")
        
        q_embed_np = np.array(query_embedding, dtype=np.float32)
        
        q_norm = np.linalg.norm(q_embed_np)
        if q_norm > 1e-8:
            q_embed_np = q_embed_np / q_norm
        else:
            self.logger.error("Query embedding has zero norm!")
            return []
        
        EXPECTED_DIM = 768
        
        for idx, (doc, meta, id_) in enumerate(zip(documents, metadatas, ids)):
            doc_embed = None
            
            if stored_embeddings and idx < len(stored_embeddings) and stored_embeddings[idx]:
                if isinstance(stored_embeddings[idx], (list, tuple)):
                    try:
                        doc_embed = np.array(stored_embeddings[idx], dtype=np.float32)
                        
                        if len(doc_embed) != EXPECTED_DIM or len(doc_embed) != len(q_embed_np):
                            doc_embed = np.array(_embed_text(doc), dtype=np.float32)
                    except (ValueError, TypeError):
                        doc_embed = np.array(_embed_text(doc), dtype=np.float32)
            
            if doc_embed is None:
                doc_embed = np.array(_embed_text(doc), dtype=np.float32)
            
            doc_norm = np.linalg.norm(doc_embed)
            if doc_norm > 1e-8:
                doc_embed = doc_embed / doc_norm
            else:
                continue
            
            similarity = float(np.dot(q_embed_np, doc_embed))
            
            if similarity >= self.similarity_threshold:
                relevant_chunks.append((doc, meta, id_, similarity))
        
        relevant_chunks.sort(key=lambda x: x[3], reverse=True)
        
        for doc, meta, id_, sim in relevant_chunks[:5]:
            print(f"✓ Chunk accepted (similarity: {sim:.3f}): {doc[:80]}...")
        
        print(f"\n📊 Found {len(relevant_chunks)} relevant chunks")
        
        return [(doc, meta, id_) for doc, meta, id_, _ in relevant_chunks]

    async def get_all_documents(self, *, notebook_id: str = "default", user_id: str = None) -> List[ChunkData]:
        try:
            from app import app
            from models import db, Chunk as ChunkModel
            
            with app.app_context():
                query = ChunkModel.query.filter_by(user_id=user_id)
                
                if notebook_id and notebook_id != "default":
                    query = query.filter_by(notebook_id=notebook_id)
                
                results = query.all()
                
                return [
                    ChunkData(
                        id=r.id,
                        text=r.content,
                        tokens=r.tokens or 0,
                        metadata=r.chunk_metadata or {}
                    )
                    for r in results
                ]
        except Exception as e:
            self.logger.error(f"Failed to get documents: {e}")
            return []

    async def delete_document(self, document_id: str, *, user_id: str = None) -> bool:
        try:
            from app import app
            from models import db, Chunk as ChunkModel
            
            with app.app_context():
                ChunkModel.query.filter_by(document_id=document_id).delete()
                db.session.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to delete document: {e}")
            return False

    async def clear_notebook(self, notebook_id: str, *, user_id: str = None) -> bool:
        try:
            from app import app
            from models import db, Chunk as ChunkModel
            
            with app.app_context():
                ChunkModel.query.filter_by(notebook_id=notebook_id, user_id=user_id).delete()
                db.session.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to clear notebook: {e}")
            return False


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="RAG Pipeline Test")
    parser.add_argument("file_path", help="Path to file (PDF, DOCX, or TXT)")
    parser.add_argument("query", help="Query to search for")
    parser.add_argument("--type", choices=["pdf", "docx", "txt", "image"], default="pdf")
    
    args = parser.parse_args()
    
    rag = RAGPipeline()
    
    async def main():
        if args.type == "image":
            with open(args.file_path, "rb") as f:
                await rag.analyze_image(f.read(), user_id="test_user")
        elif args.type == "pdf":
            await rag.ingest_pdf(args.file_path, user_id="test_user")
        elif args.type == "docx":
            await rag.ingest_docx(args.file_path, user_id="test_user")
        else:
            with open(args.file_path, "r") as f:
                await rag.ingest_txt(f.read(), user_id="test_user")
        
        result = await rag.query(args.query, user_id="test_user")
        print(f"\nAnswer: {result['answer']}")
    
    asyncio.run(main())

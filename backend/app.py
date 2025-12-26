# backend/app.py
from flask import Flask, request, jsonify, send_file, Response, session
from flask_cors import CORS
from med_bot3.chatbot import ChatBot
from med_bot3.tts_elevenlabs import generate_teen_voice
try:
    from med_bot3.stt_whisper import transcribe_audio
except ImportError:
    transcribe_audio = None
    print("Warning: stt_whisper not available (requires torch)")
from med_bot3.exam_feature.exam_generator import ExamGenerator, ExamConfig, Difficulty
from med_bot3.rag_flashcards import RAGFlashcards
from med_bot3.study_planner import StudyPlanner
from supabase import create_client, Client
import os
import asyncio
import io
import json
import datetime
import uuid
from functools import wraps
from pathlib import Path
from werkzeug.middleware.proxy_fix import ProxyFix
import logging

logging.basicConfig(level=logging.DEBUG)

FRONTEND_BUILD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'build'))
app = Flask(__name__, static_folder=os.path.join(FRONTEND_BUILD_DIR, 'static'), static_url_path='/static')
app.secret_key = os.environ.get("SESSION_SECRET")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    'pool_pre_ping': True,
    "pool_recycle": 300,
}

from models import db, User, EmailVerificationToken, Notebook, Document, Chunk
db.init_app(app)

from replit_auth import init_login_manager, make_replit_blueprint, get_current_user_api
from flask_login import current_user, login_required, login_user
from email_service import send_verification_email
import jwt

init_login_manager(app)

def get_authenticated_user_id():
    """Get user_id from current_user session (Replit database authentication)"""
    if current_user.is_authenticated:
        return current_user.id
    return None

with app.app_context():
    db.create_all()
    logging.info("Database tables created")

app.register_blueprint(make_replit_blueprint(), url_prefix="/auth")

@app.before_request
def make_session_permanent():
    session.permanent = True
    # Configure session cookie settings for cross-origin requests
    app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Configure CORS to allow all origins for development
CORS(app, 
     origins="*",
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization", "Access-Control-Allow-Credentials"],
     supports_credentials=True)

# Initialize components
api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is required")

# Initialize Supabase client
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_KEY')
if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")

supabase: Client = create_client(supabase_url, supabase_key)

chatbot = ChatBot(api_key)
exam_generator = ExamGenerator(api_key)
# Add StudyPlanner instance for API use
study_planner = StudyPlanner(api_key)

# Helper functions for user/notebook management
def get_or_create_notebook(user_id: str, notebook_name: str = "Default Notebook") -> str:
    """Get or create a notebook for the user"""
    try:
        user = User.query.get(user_id)
        if not user:
            user = User(id=user_id, email=None)
            db.session.add(user)
            db.session.flush()
        
        notebook = Notebook.query.filter_by(user_id=user_id, name=notebook_name).first()
        
        if notebook:
            return notebook.id
        
        notebook = Notebook(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=notebook_name,
            description=f'Default notebook for user {user_id}',
            color='#4285f4'
        )
        db.session.add(notebook)
        db.session.commit()
        return notebook.id
    except Exception as e:
        db.session.rollback()
        print(f"Error creating notebook: {e}")
        return str(uuid.uuid4())

def upload_to_supabase_storage(file_path: str, user_id: str, filename: str) -> str:
    """Upload file to Supabase storage and return the storage path"""
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Create storage path: {user_id}/{filename} (bucket name 'documents' is already specified)
        storage_path = f"{user_id}/{filename}"
        
        # Upload to Supabase storage
        result = supabase.storage.from_('documents').upload(storage_path, file_data)
        
        if result.get('error'):
            print(f"Storage upload warning: {result['error']}")
            # Don't raise exception, just log the warning and continue
            # The file might still be uploaded successfully
        
        print(f"Storage upload result: {result}")
        return storage_path
    except Exception as e:
        print(f"Error uploading to storage: {e}")
        # Still return the storage path so processing can continue
        storage_path = f"{user_id}/{filename}"
        print(f"Continuing with storage path: {storage_path}")
        return storage_path

# Supabase service user for FK constraints workaround
SUPABASE_SERVICE_USER_ID = 'c04c5c6a-367b-4322-8913-856d13a2da75'

def get_owner_metadata(real_user_id):
    """Create metadata JSON with real owner"""
    return f'{{"real_owner":"{real_user_id}"}}'

def extract_real_owner(field_value):
    """Extract real owner from metadata or description field
    Handles formats:
    - '{"real_owner":"uuid"}' (pure JSON metadata field)
    - '{"real_owner":"uuid"}|description text' (JSON prefix in description with separator)
    Returns None if no owner metadata found (legacy record)
    """
    if not field_value:
        return None
    # Only parse if it looks like our metadata format
    if not field_value.startswith('{"real_owner"'):
        return None
    try:
        import json
        # Check if it's prefixed format with separator
        if '|' in field_value:
            json_part = field_value.split('|')[0]
        else:
            json_part = field_value
        data = json.loads(json_part)
        return data.get('real_owner')
    except:
        return None

def extract_description(field_value):
    """Extract actual description from field that may have JSON prefix
    Returns original description for legacy records without metadata prefix
    """
    if not field_value:
        return ''
    # Only strip if it starts with our metadata format
    if field_value.startswith('{"real_owner"'):
        if '|' in field_value:
            parts = field_value.split('|', 1)
            return parts[1] if len(parts) > 1 else ''
        return ''  # Pure metadata, no description
    # Legacy record - return as-is
    return field_value

def create_document_record(user_id: str, notebook_id: str, filename: str, original_filename: str, 
                          file_type: str, file_size: int, storage_path: str) -> str:
    """Create a document record in Supabase using service user"""
    try:
        document_id = str(uuid.uuid4())
        public_url = f"{supabase_url}/storage/v1/object/public/documents/{storage_path}"
        
        # Create document in Supabase using service user to bypass FK constraint
        doc_data = {
            'id': document_id,
            'user_id': SUPABASE_SERVICE_USER_ID,  # Use service user for FK
            'notebook_id': notebook_id,
            'filename': filename,
            'original_filename': original_filename,
            'content_type': file_type,
            'file_size': file_size,
            'storage_path': storage_path,
            'status': 'pending',
            'metadata': get_owner_metadata(user_id)  # Store real owner
        }
        
        response = supabase.table('documents').insert(doc_data).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0].get('id')
        else:
            raise Exception("Failed to create document in Supabase")
    except Exception as e:
        print(f"Error creating document record: {e}")
        raise e

def update_document_status(document_id: str, status: str, error: str = None):
    """Update document processing status in Supabase"""
    try:
        update_data = {'status': status}
        if error:
            update_data['error_message'] = error
        
        supabase.table('documents').update(update_data).eq('id', document_id).execute()
    except Exception as e:
        print(f"Error updating document status: {e}")

async def initialize_exam_generator():
    """Initialize the exam generator by ingesting all existing course content files."""
    course_content_dir = Path("course_content")
    if not course_content_dir.exists():
        print("Course content directory not found, creating it...")
        course_content_dir.mkdir(exist_ok=True)
        return
    
    # Get all files in the course content directory
    files = list(course_content_dir.glob("*"))
    pdf_files = [f for f in files if f.suffix.lower() == '.pdf']
    
    if not pdf_files:
        print("No PDF files found in course_content directory")
        return
    
    print(f"Found {len(pdf_files)} PDF files to ingest...")
    
    # Ingest each PDF file
    for pdf_file in pdf_files:
        try:
            print(f"Ingesting {pdf_file.name}...")
            await exam_generator.rag.ingest_pdf(str(pdf_file), notebook_id=None)
            print(f"✓ Successfully ingested {pdf_file.name}")
        except Exception as e:
            print(f"✗ Failed to ingest {pdf_file.name}: {str(e)}")
    
    print(f"Initialization complete. Ingested {len(pdf_files)} files.")

# Initialize the exam generator (without auto-ingesting course content)
print("Exam generator ready (course content will be ingested on-demand).")

def async_route(f):
    """Decorator to handle async routes in Flask"""
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(f(*args, **kwargs))
        finally:
            loop.close()
    wrapper.__name__ = f.__name__
    return wrapper

@app.route('/api/chat', methods=['POST'])
@async_route
async def chat():
    try:
        data = request.json
        question = data.get('message')
        notebook_id = data.get('notebook_id')
        
        # Use authenticated user_id from session, ignore client-supplied value
        user_id = get_authenticated_user_id()
        
        if not question:
            return jsonify({'error': 'No message provided'}), 400
        
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Get or create notebook if not provided
        if not notebook_id:
            notebook_id = get_or_create_notebook(user_id)
        
        # Get response from chatbot with user isolation
        response = await chatbot.ask_question(question, notebook_id=notebook_id)
        
        # Ensure the response is always a dict with 'answer' and 'videos'
        if isinstance(response, dict) and 'answer' in response:
            return jsonify(response)
        else:
            return jsonify({'answer': response, 'videos': []})
    except Exception as e:
        print(f"Chat Error: {e}")  # Add logging
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/stream', methods=['POST'])
@async_route
async def chat_stream():
    """
    Streaming chat endpoint using Server-Sent Events (SSE)
    Streams real-time updates from the multi-hop RAG pipeline
    """
    try:
        data = request.json
        question = data.get('message')
        notebook_id = data.get('notebook_id')
        
        # Use authenticated user_id from session, ignore client-supplied value
        user_id = get_authenticated_user_id()
        
        if not question:
            return jsonify({'error': 'No message provided'}), 400
        
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Get or create notebook if not provided
        if not notebook_id:
            notebook_id = get_or_create_notebook(user_id)
        
        # For now, just use the regular chat endpoint
        # In the future, this can be enhanced with real streaming
        response = await chatbot.ask_question(question, notebook_id=notebook_id)
        
        # Debug: Log videos if present
        if isinstance(response, dict) and 'videos' in response:
            videos = response.get('videos', [])
            print(f"Stream endpoint: Found {len(videos)} videos in response")
            if videos:
                print(f"Stream endpoint: Video links: {[v.get('link', 'N/A') for v in videos]}")
        
        # Create a simple streaming response
        def generate_stream():
            # Send initial update
            yield f"data: {json.dumps({'type': 'query_start', 'question': question})}\n\n"
            
            # Send completion update with videos if available
            if isinstance(response, dict) and 'answer' in response:
                videos = response.get('videos', [])
                print(f"Stream endpoint: Sending {len(videos)} videos in query_complete event")
                yield f"data: {json.dumps({'type': 'query_complete', 'answer': response['answer'], 'videos': videos})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'query_complete', 'answer': str(response), 'videos': []})}\n\n"
            
            # Send final completion signal
            yield f"data: {json.dumps({'type': 'stream_complete'})}\n\n"
        
        return Response(
            generate_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
            }
        )
        
    except Exception as e:
        print(f"Stream Chat Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
@async_route
async def upload_document():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Use authenticated user_id from session, ignore client-supplied value
        user_id = get_authenticated_user_id()
        notebook_id = request.form.get('notebook_id')
        notebook_name = request.form.get('notebook_name', 'Default Notebook')
        
        print(f"/api/upload user_id: {user_id}, notebook_id: {notebook_id}")
        
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Get or create notebook
        if not notebook_id:
            notebook_id = get_or_create_notebook(user_id, notebook_name)
            print(f"Using notebook ID: {notebook_id}")
        
        # Generate unique filename to avoid conflicts
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Save file temporarily for processing
        temp_dir = 'temp_uploads'
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, unique_filename)
        file.save(temp_path)
        
        try:
            # Get file info
            file_size = os.path.getsize(temp_path)
            file_type = file.content_type or 'application/octet-stream'
            
            # Upload to Supabase storage
            print(f"Uploading to Supabase storage: {unique_filename}")
            storage_path = upload_to_supabase_storage(temp_path, user_id, unique_filename)
            
            # Create document record in database
            print(f"Creating document record in database")
            document_id = create_document_record(
                user_id=user_id,
                notebook_id=notebook_id,
                filename=unique_filename,
                original_filename=file.filename,
                file_type=file_type,
                file_size=file_size,
                storage_path=storage_path
            )
            
            # Process the file with RAG pipeline
            print(f"Processing file with RAG pipeline: {temp_path}")
            update_document_status(document_id, 'processing')
            
            # Process based on file type
            print(f"Processing file type: {file_extension.lower()}")
            print(f"Using notebook_id: {notebook_id}, user_id: {user_id}")
            
            if file_extension.lower() == '.pdf':
                print("Processing as PDF...")
                success = await chatbot.upload_document(temp_path, notebook_id=notebook_id, user_id=user_id)
            elif file_extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                print("Processing as image...")
                from PIL import Image
                image = Image.open(temp_path)
                await chatbot.rag.analyze_image(image, notebook_id=notebook_id, user_id=user_id)
                success = True
            else:
                # For other file types, try text processing
                print("Processing as text...")
                success = await chatbot.upload_document(temp_path, notebook_id=notebook_id, user_id=user_id)
            
            print(f"RAG processing result: {success}")
            
            if success:
                # Update chunks with the document_id
                print(f"Linking chunks to document_id: {document_id}")
                try:
                    # Update all chunks for this notebook and user that don't have a document_id
                    result = supabase.table('chunks').update({'document_id': document_id}).eq('notebook_id', notebook_id).eq('user_id', user_id).is_('document_id', 'null').execute()
                    print(f"Updated {len(result.data) if result.data else 0} chunks with document_id")
                except Exception as e:
                    print(f"Warning: Failed to link chunks to document: {e}")
                
                update_document_status(document_id, 'completed')
                return jsonify({
                    'message': 'File uploaded and processed successfully',
                    'filename': file.filename,
                    'document_id': document_id,
                    'storage_path': storage_path
                })
            else:
                update_document_status(document_id, 'failed', 'RAG processing failed')
                return jsonify({'error': 'Failed to process file with RAG pipeline'}), 500
                
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        print(f"Upload Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Update document status if we have a document_id
        if 'document_id' in locals():
            update_document_status(document_id, 'failed', str(e))
        
        return jsonify({'error': 'Failed to process file', 'detail': str(e)}), 500

@app.route('/api/documents', methods=['GET'])
def list_documents():
    """List documents from Supabase using service user workaround"""
    try:
        user_data = get_current_user_api()
        user_id = user_data.get('id') if user_data else request.args.get('user_id')
        notebook_id = request.args.get('notebook_id')
        
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        result = []
        
        # Query documents under service user
        query = supabase.table('documents').select('*').eq('user_id', SUPABASE_SERVICE_USER_ID)
        if notebook_id:
            query = query.eq('notebook_id', notebook_id)
        response = query.order('created_at', desc=True).execute()
        
        if response.data:
            for doc in response.data:
                metadata = doc.get('metadata') or ''
                real_owner = extract_real_owner(metadata)
                if real_owner == user_id:
                    result.append({
                        'id': doc.get('id'),
                        'user_id': user_id,
                        'notebook_id': doc.get('notebook_id'),
                        'filename': doc.get('original_filename') or doc.get('filename'),
                        'original_filename': doc.get('original_filename'),
                        'storage_path': doc.get('storage_path'),
                        'content_type': doc.get('content_type'),
                        'file_size': doc.get('file_size'),
                        'status': doc.get('status', 'completed'),
                        'error_message': doc.get('error_message'),
                        'created_at': doc.get('created_at'),
                        'updated_at': doc.get('updated_at')
                    })
        
        # Also check for legacy documents under user's direct ownership
        try:
            legacy_query = supabase.table('documents').select('*').eq('user_id', user_id)
            if notebook_id:
                legacy_query = legacy_query.eq('notebook_id', notebook_id)
            legacy_response = legacy_query.order('created_at', desc=True).execute()
            
            if legacy_response.data:
                for doc in legacy_response.data:
                    if not any(r['id'] == doc.get('id') for r in result):
                        result.append({
                            'id': doc.get('id'),
                            'user_id': doc.get('user_id'),
                            'notebook_id': doc.get('notebook_id'),
                            'filename': doc.get('original_filename') or doc.get('filename'),
                            'original_filename': doc.get('original_filename'),
                            'storage_path': doc.get('storage_path'),
                            'content_type': doc.get('content_type'),
                            'file_size': doc.get('file_size'),
                            'status': doc.get('status', 'completed'),
                            'error_message': doc.get('error_message'),
                            'created_at': doc.get('created_at'),
                            'updated_at': doc.get('updated_at')
                        })
        except:
            pass  # User might not exist in Supabase users table
        
        return jsonify(result)
    except Exception as e:
        print(f"Documents Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts', methods=['POST'])
@async_route
async def tts():
    try:
        data = request.json
        text = data.get('text')
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Generate audio using TTS
        audio_bytes = await asyncio.to_thread(generate_teen_voice, text)
        
        return send_file(
            io.BytesIO(audio_bytes),
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name='output.mp3'
        )
    except Exception as e:
        print(f"TTS Error: {e}")  # Add logging
        return jsonify({'error': str(e)}), 500

@app.route('/api/stt', methods=['POST'])
@async_route
async def stt():
    try:
        if transcribe_audio is None:
            return jsonify({'error': 'Speech-to-text is not available (requires torch)'}), 503
        
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Get the audio format from the filename or content type
        audio_format = 'webm'  # Default format from browser recording
        if audio_file.content_type:
            if 'webm' in audio_file.content_type:
                audio_format = 'webm'
            elif 'wav' in audio_file.content_type:
                audio_format = 'wav'
            elif 'mp3' in audio_file.content_type:
                audio_format = 'mp3'
        
        # Read the audio data
        audio_data = audio_file.read()
        
        # Transcribe the audio using async wrapper
        transcribed_text = await asyncio.to_thread(transcribe_audio, audio_data, audio_format)
        
        return jsonify({'text': transcribed_text})
    except Exception as e:
        print(f"STT Error: {e}")  # Add logging
        return jsonify({'error': str(e)}), 500

@app.route('/api/exam-pdf', methods=['POST'])
def exam_pdf():
    try:
        data = request.json
        difficulty_str = data.get('difficulty')
        num_questions = data.get('num_questions')
        topic = data.get('topic')
        format_type = data.get('format', 'PDF')  # Default to PDF for backward compatibility
        example_exam_filename = data.get('example_exam_filename')
        example_exam_text = data.get('example_exam_text')
        
        if not (difficulty_str and num_questions and topic):
            return jsonify({'error': 'Missing required parameters: difficulty, num_questions, topic'}), 400
        difficulty_str = difficulty_str.upper()
        if difficulty_str not in Difficulty.__members__:
            return jsonify({'error': 'Invalid difficulty'}), 400
        difficulty = Difficulty[difficulty_str]
        try:
            num_questions = int(num_questions)
        except Exception:
            return jsonify({'error': 'num_questions must be an integer'}), 400

        # --- NEW: Handle example exam upload if provided ---
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if example_exam_text:
                # Direct text input for example exam
                loop.run_until_complete(exam_generator.upload_extra_files(text_content=example_exam_text, file_type="example"))
            elif example_exam_filename:
                # File-based example exam (now from example_exams directory)
                file_path = os.path.join('exam_generation_feature', 'example_exams', example_exam_filename)
                if not os.path.exists(file_path):
                    return jsonify({'error': f'Example exam file {example_exam_filename} not found in example_exams/'}), 400
                loop.run_until_complete(exam_generator.upload_extra_files(file_path=file_path, file_type="example"))
        finally:
            loop.close()
        # --- END NEW ---

        # Get notebook_id and user_id from request if provided
        notebook_id = data.get('notebook_id')
        user_id = data.get('user_id')
        
        print(f"Exam generation request - topic: {topic}, notebook_id: {notebook_id}, user_id: {user_id}")
        
        # Use the same logic as the CLI: get content via RAG pipeline
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            content = loop.run_until_complete(exam_generator.get_content(topic, notebook_id=notebook_id, user_id=user_id))
            print(f"Exam generation - retrieved content length: {len(content) if content else 0} characters")
        finally:
            loop.close()
        if not content:
            error_msg = f'No content found for the topic "{topic}". '
            if notebook_id:
                error_msg += f'Please make sure you have uploaded documents to your notebook (ID: {notebook_id}) and they have been processed.'
            else:
                error_msg += 'Please make sure you have uploaded documents and they have been processed.'
            return jsonify({'error': error_msg}), 400
        # Optionally truncate content to avoid token overflow
        MAX_TOKENS = 1000000
        words = content.split()
        if len(words) > MAX_TOKENS:
            content = ' '.join(words[:MAX_TOKENS])

        # --- NEW: Set use_example_questions based on presence of example exam ---
        example_files = [f.name for f in exam_generator.example_exams_dir.glob("*")]
        use_example_questions = bool(example_files) or bool(exam_generator.example_exam_text)
        # --- END NEW ---

        config = ExamConfig(
            difficulty=difficulty,
            num_questions=num_questions,
            topic=topic,
            use_example_questions=use_example_questions,
            use_study_guide=False  # Could be extended for study guide support
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            exam = loop.run_until_complete(exam_generator.generate_exam(config, content))
        finally:
            loop.close()
        
        # Return based on format type
        if format_type.upper() == 'TEXT':
            # Return exam as plain text
            return exam, 200, {'Content-Type': 'text/plain'}
        else:
            # Return PDF (default behavior)
            pdf_path = exam_generator._generate_pdf(exam, config)
            return send_file(pdf_path, mimetype='application/pdf', as_attachment=True, download_name='exam.pdf')
    except Exception as e:
        print(f"Exam PDF Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/flashcards', methods=['POST'])
@async_route
async def flashcards():
    try:
        data = request.json
        print(f"Flashcards request data: {data}")  # Debug log
        topic = data.get('topic')
        filename = data.get('filename')
        num_cards = int(data.get('num_cards', 8))
        notebook_id = data.get('notebook_id')
        
        # Use authenticated user_id from session
        user_id = get_authenticated_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        print(f"Topic: {topic}, Filename: {filename}, Num cards: {num_cards}, Notebook: {notebook_id}")  # Debug log
        
        if not topic or not filename:
            print(f"Missing required fields - Topic: {topic}, Filename: {filename}")  # Debug log
            return jsonify({'error': 'Missing topic or filename'}), 400
        
        if not notebook_id:
            print("Missing notebook_id")  # Debug log
            return jsonify({'error': 'Missing notebook_id'}), 400
        
        # Use the provided notebook_id directly (it's already a UUID)
        notebook_uuid = notebook_id
        
        # Check if document exists in database
        try:
            # First, let's see what documents are in this notebook
            all_docs = supabase.table('documents').select('*').eq('notebook_id', notebook_uuid).execute()
            print(f"All documents in notebook {notebook_id}: {[doc['filename'] for doc in all_docs.data]}")
            
            # Try to find the document by filename (exact match)
            result = supabase.table('documents').select('*').eq('filename', filename).eq('notebook_id', notebook_uuid).execute()
            
            # If not found by filename, try by original_filename
            if not result.data:
                print(f"Not found by filename, trying original_filename...")
                result = supabase.table('documents').select('*').eq('original_filename', filename).eq('notebook_id', notebook_uuid).execute()
            
            # If still not found, try partial match
            if not result.data:
                print(f"Not found by exact match, trying partial match...")
                result = supabase.table('documents').select('*').ilike('filename', f'%{filename}%').eq('notebook_id', notebook_uuid).execute()
            
            if not result.data:
                print(f"Document {filename} not found in database for notebook {notebook_id}")  # Debug log
                # Get available files in this notebook for better error message
                try:
                    available_docs = supabase.table('documents').select('filename, original_filename').eq('notebook_id', notebook_uuid).execute()
                    available_files = [doc.get('original_filename') or doc.get('filename') for doc in available_docs.data]
                    return jsonify({
                        'error': f'File "{filename}" not found in this notebook. Available files: {", ".join(available_files[:5])}{"..." if len(available_files) > 5 else ""}'
                    }), 400
                except:
                    return jsonify({'error': f'File {filename} not found in your notebooks'}), 400
            
            document = result.data[0]
            print(f"Found document: {document['filename']} in notebook {notebook_id}")  # Debug log
            
            # Check if document has been processed (has chunks)
            chunks_result = supabase.table('chunks').select('id').eq('document_id', document['id']).limit(1).execute()
            
            if not chunks_result.data:
                print(f"No chunks found for document {filename}")  # Debug log
                print(f"Document ID: {document['id']}")
                print(f"Document status: {document.get('processing_status', 'unknown')}")
                
                # Check if there are any chunks for this document at all
                all_chunks = supabase.table('chunks').select('*').eq('document_id', document['id']).execute()
                print(f"All chunks for this document: {len(all_chunks.data)}")
                
                # Try to find another document in the same notebook that has chunks
                print(f"Looking for alternative documents with chunks in notebook {notebook_uuid}...")
                all_docs = supabase.table('documents').select('*').eq('notebook_id', notebook_uuid).execute()
                print(f"All documents in notebook {notebook_uuid}: {[doc['filename'] for doc in all_docs.data]}")
                
                # Find a document that actually has chunks
                alternative_document = None
                for doc in all_docs.data:
                    doc_chunks = supabase.table('chunks').select('id').eq('document_id', doc['id']).limit(1).execute()
                    if doc_chunks.data:
                        print(f"Found alternative document with chunks: {doc['filename']}")
                        alternative_document = doc
                        break
                
                if alternative_document:
                    print(f"Using alternative document: {alternative_document['filename']}")
                    document = alternative_document
                else:
                    return jsonify({'error': f'File {filename} has not been processed yet. Please use the reprocess button in the files dropdown to process this document for flashcards.'}), 400
            
            print(f"Found {len(chunks_result.data)} chunks for document {filename}")  # Debug log
            
        except Exception as db_error:
            print(f"Database error: {db_error}")  # Debug log
            return jsonify({'error': f'Error accessing file information: {str(db_error)}'}), 400
        
        # Generate flashcards using existing chunks
        try:
            # Create RAG instance
            rag = RAGFlashcards()
            
            # Generate flashcards using existing chunks (no need to re-ingest)
            print(f"Generating flashcards for topic: {topic}")  # Debug log
            cards = await rag.generate_flashcards(topic=topic, notebook_id=notebook_uuid, num_cards=num_cards, user_id=user_id)
            print(f"Generated {len(cards)} flashcards")  # Debug log
            
            return jsonify({'flashcards': cards})
            
        except Exception as rag_error:
            print(f"RAG error: {rag_error}")  # Debug log
            return jsonify({'error': f'Failed to generate flashcards: {str(rag_error)}'}), 500
            
    except Exception as e:
        print(f"Flashcards Error: {e}")
        import traceback
        traceback.print_exc()  # Print full traceback
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-example-exam', methods=['POST'])
def upload_example_exam():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        # Save the file to the example_exams directory
        os.makedirs('exam_generation_feature/example_exams', exist_ok=True)
        save_path = os.path.join('exam_generation_feature', 'example_exams', file.filename)
        file.save(save_path)
        return jsonify({'filename': file.filename})
    except Exception as e:
        print(f"Upload Example Exam Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/studyplan', methods=['POST'])
@async_route
async def studyplan():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        # Save the file to course_content directory (consistent with other endpoints)
        os.makedirs('course_content', exist_ok=True)
        save_path = os.path.join('course_content', file.filename)
        file.save(save_path)
        # Get weeks parameter (optional)
        weeks = request.form.get('weeks', 16)
        try:
            weeks = int(weeks)
        except Exception:
            weeks = 16
        # Generate study plan (PDF + events)
        result = await study_planner.create_study_plan_for_api(save_path, semester_weeks=weeks)
        print(f"Study plan result: {result}")
        if not result or not isinstance(result, tuple) or len(result) != 2:
            print(f"Invalid result format: {result}")
            return jsonify({'error': 'Failed to generate study plan'}), 500
        pdf_path, events = result
        print(f"PDF path: {pdf_path}")
        print(f"Events type: {type(events)}")
        print(f"Events count: {len(events) if events else 0}")
        if not pdf_path or not events:
            print(f"Missing data - PDF path: {pdf_path}, Events: {events}")
            return jsonify({'error': 'Failed to generate study plan'}), 500
        
        # Debug: Check if PDF file exists and has content
        if pdf_path and os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            print(f"Generated PDF: {pdf_path}, size: {file_size} bytes")
        else:
            print(f"PDF file not found or empty: {pdf_path}")
            return jsonify({'error': 'PDF file not generated correctly'}), 500
        
        # Return both PDF and events (PDF as file, events as JSON)
        # Option 1: Return JSON with download URL and events
        # Option 2: Return PDF directly (not suitable for frontend display + events)
        # We'll return JSON with a download URL and the events
        pdf_url = f"/api/download-studyplan/{os.path.basename(pdf_path)}"
        print(f"PDF URL: {pdf_url}")
        print(f"Returning {len(events)} events to frontend")
        print(f"Sample event structure: {events[0] if events else 'No events'}")
        return jsonify({'pdf_url': pdf_url, 'events': events})
    except Exception as e:
        print(f"StudyPlan Error: {e}")
        return jsonify({'error': str(e)}), 500
'''    
{
    "notebookId": "string",
    "title": "string",
    "semesterWeeks": 0,
    "syllabusContent": "string",
    "smartScheduling": false,
    "calendarType": "string",
    "calendarEmail": "string", 
    {
        "success": true,
        "events": [
            {
                "title": "string",
                "description": "string",
                "start_datetime": "string",
                "end_datetime": "string"
            }
        ],
        "event_count": 0,
        "filename": "string",
        "pdf_path": "string",
        "pdf_available": true
    }
}
'''

@app.route('/api/studyplan-upload', methods=['POST'])
@async_route
async def studyplan_upload():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        os.makedirs('course_content', exist_ok=True)
        save_path = os.path.join('course_content', file.filename)
        file.save(save_path)
        # Use default 16 weeks for now
        result = await study_planner.create_study_plan_for_api(save_path, semester_weeks=16)
        print(f"Study plan upload result: {result}")
        if not result or not isinstance(result, tuple) or len(result) != 2:
            print(f"Invalid result format: {result}")
            return jsonify({'error': 'Failed to generate study plan'}), 500
        pdf_path, events = result
        print(f"PDF path: {pdf_path}")
        print(f"Events count: {len(events) if events else 0}")
        if not pdf_path or not events:
            print(f"Missing data - PDF path: {pdf_path}, Events: {events}")
            return jsonify({'error': 'Failed to generate study plan'}), 500
        pdf_url = f"/api/download-studyplan/{os.path.basename(pdf_path)}"
        print(f"PDF URL (upload): {pdf_url}")
        print(f"Returning {len(events)} events to frontend")
        return jsonify({'pdf_url': pdf_url, 'events': events})
    except Exception as e:
        print(f"StudyPlanUpload Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-studyplan/<filename>', methods=['GET'])
def download_studyplan(filename):
    try:
        file_path = os.path.join('study_plans', filename)
        print(f"Attempting to download file: {file_path}")
        print(f"File exists: {os.path.exists(file_path)}")
        
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return jsonify({'error': 'File not found'}), 404
        
        # Check file size
        file_size = os.path.getsize(file_path)
        print(f"File size: {file_size} bytes")
        
        if file_size == 0:
            print(f"File is empty: {file_path}")
            return jsonify({'error': 'File is empty'}), 500
        
        # Read the file content to verify it's a valid PDF
        try:
            with open(file_path, 'rb') as f:
                content = f.read(1024)  # Read first 1KB
                if not content.startswith(b'%PDF'):
                    print(f"File is not a valid PDF: {file_path}")
                    return jsonify({'error': 'File is not a valid PDF'}), 500
        except Exception as e:
            print(f"Error reading file: {e}")
            return jsonify({'error': 'Error reading file'}), 500
        
        # Set proper headers for PDF download
        response = send_file(
            file_path, 
            mimetype='application/pdf', 
            as_attachment=True, 
            download_name=filename
        )
        
        # Add additional headers for better compatibility
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        print(f"Successfully serving PDF: {filename}")
        return response
        
    except Exception as e:
        print(f"Download StudyPlan Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/studyplan/add-to-calendar', methods=['POST'])
@async_route
async def add_study_plan_to_calendar():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        events = data.get('events', [])
        calendar_type = data.get('calendar_type', 'gmail')  # Default to gmail
        email = data.get('email', '')
        
        if not events:
            return jsonify({'error': 'No events provided'}), 400
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        if calendar_type not in ['gmail', 'outlook']:
            return jsonify({'error': 'Invalid calendar type. Use "gmail" or "outlook"'}), 400
        
        # Authenticate with the calendar service
        auth_success = await study_planner._ensure_calendar_auth(calendar_type, email)
        if not auth_success:
            return jsonify({'error': f'Failed to authenticate with {calendar_type.title()} calendar'}), 401
        
        # Process and add events to calendar
        processed_calendar_events = []
        for event_template in events:
            try:
                if calendar_type == "gmail":
                    # Validate datetime format
                    datetime.datetime.fromisoformat(event_template["start_datetime"].replace("Z", "+00:00"))
                    datetime.datetime.fromisoformat(event_template["end_datetime"].replace("Z", "+00:00"))
                    calendar_event_input = {
                        "calendar_id": "primary",
                        "summary": event_template["summary"],
                        "description": event_template.get("description", ""),
                        "start_datetime": event_template["start_datetime"],
                        "end_datetime": event_template["end_datetime"],
                    }
                else:  # outlook
                    calendar_event_input = {
                        "subject": event_template["summary"],
                        "body": event_template.get("description", ""),
                        "start_date_time": event_template["start_datetime"].split(".")[0],
                        "end_date_time": event_template["end_datetime"].split(".")[0],
                    }
                processed_calendar_events.append(calendar_event_input)
            except KeyError as e:
                print(f"Skipping calendar event due to missing key: {e}. Event data: {event_template}")
            except ValueError as e:
                print(f"Skipping calendar event due to invalid datetime format: {e}. Event data: {event_template}")
        
        if not processed_calendar_events:
            return jsonify({'error': 'No valid events to add to calendar after processing'}), 400
        
        # Add events to calendar
        successful_adds = 0
        failed_events = []
        
        for event_data in processed_calendar_events:
            try:
                print(f"Adding event to {calendar_type.title()} Calendar: {event_data.get('summary', event_data.get('subject', ''))}")
                if await study_planner._add_event_to_calendar(event_data, calendar_type):
                    successful_adds += 1
                else:
                    failed_events.append(event_data.get('summary', event_data.get('subject', 'Unknown')))
            except Exception as e:
                print(f"Error adding event to calendar: {str(e)}")
                failed_events.append(event_data.get('summary', event_data.get('subject', 'Unknown')))
        
        return jsonify({
            'success': True,
            'message': f'Successfully added {successful_adds} out of {len(processed_calendar_events)} events to your {calendar_type.title()} Calendar.',
            'successful_adds': successful_adds,
            'total_events': len(processed_calendar_events),
            'failed_events': failed_events
        })
        
    except Exception as e:
        print(f"Add to Calendar Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# Notebook management endpoints - Uses Supabase with service user workaround
@app.route('/api/notebooks', methods=['GET'])
def list_notebooks():
    """List all notebooks for the authenticated user from Supabase"""
    try:
        user_data = get_current_user_api()
        user_id = user_data.get('id') if user_data else request.args.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Query Supabase - get all notebooks under service user
        response = supabase.table('notebooks').select('*').eq('user_id', SUPABASE_SERVICE_USER_ID).order('created_at', desc=True).execute()
        notebooks = response.data if response.data else []
        
        # Filter by real owner stored in description field
        result = []
        for nb in notebooks:
            desc_field = nb.get('description', '')
            real_owner = extract_real_owner(desc_field)
            # Include only if real owner matches this user
            if real_owner == user_id:
                result.append({
                    'id': nb.get('id'),
                    'user_id': user_id,  # Return real user id
                    'name': nb.get('name'),
                    'description': extract_description(desc_field),  # Extract clean description
                    'color': nb.get('color', '#4285f4'),
                    'created_at': nb.get('created_at'),
                    'updated_at': nb.get('updated_at')
                })
        
        # Also check for legacy notebooks under the user's own ID
        try:
            legacy_response = supabase.table('notebooks').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            if legacy_response.data:
                for nb in legacy_response.data:
                    if not any(r['id'] == nb.get('id') for r in result):
                        result.append({
                            'id': nb.get('id'),
                            'user_id': nb.get('user_id'),
                            'name': nb.get('name'),
                            'description': nb.get('description', ''),
                            'color': nb.get('color', '#4285f4'),
                            'created_at': nb.get('created_at'),
                            'updated_at': nb.get('updated_at')
                        })
        except:
            pass  # User might not exist in Supabase users table
        
        return jsonify(result)
    except Exception as e:
        print(f"Notebooks Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notebooks', methods=['POST'])
def create_notebook():
    """Create a new notebook in Supabase using service user"""
    try:
        data = request.json or {}
        
        user_data = get_current_user_api()
        user_id = user_data.get('id') if user_data else data.get('user_id')
        
        name = data.get('name')
        description = data.get('description', '')
        color = data.get('color', '#4285f4')
        
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
            
        if not name:
            return jsonify({'error': 'name is required'}), 400
        
        # Ensure user exists in local DB for auth purposes
        user = User.query.get(user_id)
        if not user:
            user = User(id=user_id, email=user_data.get('email') if user_data else None)
            db.session.add(user)
            db.session.commit()
        
        # Create notebook in Supabase using service user to bypass FK constraint
        # Store real owner in description field as JSON prefix
        notebook_id = str(uuid.uuid4())
        owner_prefix = get_owner_metadata(user_id)
        notebook_data = {
            'id': notebook_id,
            'user_id': SUPABASE_SERVICE_USER_ID,  # Use service user for FK
            'name': name,
            'description': f"{owner_prefix}|{description}" if description else owner_prefix,  # Embed owner in description
            'color': color
        }
        
        response = supabase.table('notebooks').insert(notebook_data).execute()
        
        if response.data and len(response.data) > 0:
            nb = response.data[0]
            return jsonify({
                'id': nb.get('id'),
                'user_id': user_id,  # Return real user id
                'name': nb.get('name'),
                'description': description,
                'color': nb.get('color', '#4285f4'),
                'created_at': nb.get('created_at'),
                'updated_at': nb.get('updated_at')
            })
        else:
            return jsonify({'error': 'Failed to create notebook'}), 500
    except Exception as e:
        print(f"Create Notebook Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notebooks/<notebook_id>', methods=['DELETE'])
def delete_notebook(notebook_id):
    """Delete a notebook from Supabase"""
    try:
        user_data = get_current_user_api()
        user_id = user_data.get('id') if user_data else request.args.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Check notebook exists and belongs to user (check both service user and direct ownership)
        check = supabase.table('notebooks').select('id,metadata,user_id').eq('id', notebook_id).execute()
        if not check.data or len(check.data) == 0:
            return jsonify({'error': 'Notebook not found'}), 404
        
        nb = check.data[0]
        real_owner = extract_real_owner(nb.get('metadata'))
        # Allow delete if real owner matches or direct ownership
        if real_owner != user_id and nb.get('user_id') != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Delete from Supabase
        supabase.table('notebooks').delete().eq('id', notebook_id).execute()
        return jsonify({'message': 'Notebook deleted successfully'})
    except Exception as e:
        print(f"Delete Notebook Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reprocess-document', methods=['POST'])
@async_route
async def reprocess_document():
    """Manually reprocess a document that doesn't have chunks"""
    try:
        data = request.json
        document_id = data.get('document_id')
        user_id = data.get('user_id')
        
        if not document_id:
            return jsonify({'error': 'Missing document_id'}), 400
            
        document = Document.query.get(document_id)
        if not document:
            return jsonify({'error': 'Document not found'}), 404
            
        print(f"Reprocessing document: {document.filename}")
        
        existing_chunks = Chunk.query.filter_by(document_id=document_id).first()
        if existing_chunks:
            chunk_count = Chunk.query.filter_by(document_id=document_id).count()
            return jsonify({'message': 'Document already has chunks', 'chunk_count': chunk_count})
        
        # Get the file from storage and reprocess
        try:
            # Download file from storage
            file_data = supabase.storage.from_('documents').download(document.storage_path)
            
            # Save to temporary file
            temp_path = f"/tmp/reprocess_{document_id}.pdf"
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            # Process with RAG
            success = await chatbot.upload_document(temp_path, notebook_id=document.notebook_id, user_id=user_id)
            
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
            if success:
                return jsonify({'message': 'Document reprocessed successfully'})
            else:
                return jsonify({'error': 'Failed to reprocess document'}), 500
                
        except Exception as e:
            print(f"Reprocessing error: {e}")
            return jsonify({'error': f'Failed to reprocess: {str(e)}'}), 500
            
    except Exception as e:
        print(f"Reprocess endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Backend is running'})

# Migration endpoint to sync documents from Supabase to local database
@app.route('/api/migrate-documents', methods=['POST'])
def migrate_documents():
    """Migrate documents from Supabase to local database"""
    try:
        user_data = get_current_user_api()
        if not user_data:
            return jsonify({'error': 'Authentication required'}), 401
        
        user_id = user_data.get('id')
        
        # Fetch documents from Supabase
        result = supabase.table('documents').select('*').eq('user_id', user_id).execute()
        
        if not result.data:
            return jsonify({'message': 'No documents to migrate', 'migrated': 0})
        
        migrated_count = 0
        skipped_count = 0
        
        for doc in result.data:
            # Check if document already exists in local database
            existing = Document.query.get(doc['id'])
            if existing:
                skipped_count += 1
                continue
            
            # Ensure notebook exists in local database
            notebook_id = doc.get('notebook_id')
            if notebook_id:
                notebook = Notebook.query.get(notebook_id)
                if not notebook:
                    # Create notebook in local database
                    notebook = Notebook(
                        id=notebook_id,
                        user_id=user_id,
                        name='Migrated Notebook',
                        description='Notebook migrated from Supabase',
                        color='#4285f4'
                    )
                    db.session.add(notebook)
                    db.session.flush()
            
            # Create document in local database
            new_doc = Document(
                id=doc['id'],
                user_id=user_id,
                notebook_id=notebook_id,
                filename=doc.get('filename', ''),
                original_filename=doc.get('original_filename', doc.get('filename', '')),
                file_type=doc.get('file_type', 'application/octet-stream'),
                file_size=doc.get('file_size', 0),
                storage_path=doc.get('storage_path', ''),
                file_path=doc.get('file_path', ''),
                processing_status=doc.get('processing_status', 'completed'),
                processing_error=doc.get('processing_error'),
                doc_metadata=doc.get('metadata', {})
            )
            db.session.add(new_doc)
            migrated_count += 1
        
        db.session.commit()
        return jsonify({
            'message': f'Migration complete',
            'migrated': migrated_count,
            'skipped': skipped_count
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Migration error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def sync_user_to_database(user_id, email=None, first_name=None, last_name=None, profile_image_url=None):
    """Sync user to local database AND Supabase users table"""
    try:
        # 1. Sync to local database (for auth purposes)
        existing_user = User.query.get(user_id)
        if not existing_user:
            new_user = User(
                id=user_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                profile_image_url=profile_image_url,
                is_email_verified=True
            )
            db.session.add(new_user)
            db.session.commit()
            print(f"User synced to local database: {user_id}")
        
        # 2. Sync to Supabase users table (for FK constraints on notebooks/documents)
        try:
            # Check if user exists in Supabase
            check = supabase.table('users').select('id').eq('id', user_id).execute()
            if not check.data or len(check.data) == 0:
                # Create user in Supabase
                user_data = {
                    'id': user_id,
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'profile_image_url': profile_image_url,
                    'is_email_verified': True
                }
                supabase.table('users').insert(user_data).execute()
                print(f"User synced to Supabase: {user_id}")
        except Exception as supabase_error:
            # If duplicate or constraint error, user already exists which is fine
            error_str = str(supabase_error).lower()
            if 'duplicate' not in error_str and '23505' not in str(supabase_error):
                print(f"Supabase user sync warning: {supabase_error}")
        
        return True
    except Exception as e:
        db.session.rollback()
        # If it's a duplicate key error, that's fine
        if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
            return True
        print(f"Error syncing user to database: {e}")
        return False

@app.route('/api/auth/sync-user', methods=['POST'])
def sync_user():
    """Sync current user to local database for foreign key relationships"""
    try:
        user_data = get_current_user_api()
        if not user_data:
            return jsonify({'error': 'Not authenticated'}), 401
        
        success = sync_user_to_database(
            user_id=user_data.get('id'),
            email=user_data.get('email'),
            first_name=user_data.get('first_name'),
            last_name=user_data.get('last_name'),
            profile_image_url=user_data.get('profile_image_url')
        )
        
        if success:
            return jsonify({'success': True, 'message': 'User synced to database'})
        else:
            return jsonify({'error': 'Failed to sync user'}), 500
    except Exception as e:
        print(f"Error in sync_user endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/user', methods=['GET'])
def get_auth_user():
    """Get current authenticated user from Replit database"""
    user_data = get_current_user_api()
    if user_data:
        # Sync user to local database on every auth check to ensure they exist
        sync_user_to_database(
            user_id=user_data.get('id'),
            email=user_data.get('email'),
            first_name=user_data.get('first_name'),
            last_name=user_data.get('last_name'),
            profile_image_url=user_data.get('profile_image_url')
        )
        return jsonify(user_data)
    return jsonify(None), 200

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Replit database email/password login endpoint"""
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find user by email in Replit database
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Check if email is verified
        if not user.is_email_verified:
            return jsonify({
                'error': 'Please verify your email before logging in',
                'requires_verification': True,
                'email': user.email
            }), 403
        
        # Log the user in using Flask-Login
        login_user(user, remember=True)
        session.permanent = True
        
        return jsonify({
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'profile_image_url': user.profile_image_url or ''
            }
        })
    except Exception as e:
        logging.error(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """Replit database email/password signup endpoint with email verification"""
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            if existing_user.is_email_verified:
                return jsonify({'error': 'Email already registered'}), 400
            else:
                # User exists but not verified - send new verification code
                token, code = EmailVerificationToken.create_for_user(existing_user.id)
                db.session.add(token)
                db.session.commit()
                
                send_verification_email(email, code, first_name or existing_user.first_name)
                
                return jsonify({
                    'message': 'Verification code sent to your email',
                    'requires_verification': True,
                    'email': email
                })
        
        # Create new user (unverified)
        user = User()
        user.id = str(uuid.uuid4())
        user.email = email
        user.set_password(password)
        user.first_name = first_name
        user.last_name = last_name
        user.is_email_verified = False
        
        db.session.add(user)
        db.session.flush()  # Get user ID before creating token
        
        # Create verification token
        token, code = EmailVerificationToken.create_for_user(user.id)
        db.session.add(token)
        db.session.commit()
        
        # Send verification email
        email_sent = send_verification_email(email, code, first_name)
        
        return jsonify({
            'message': 'Account created! Please check your email for a verification code.',
            'requires_verification': True,
            'email': email,
            'email_sent': email_sent
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Signup error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/verify-email', methods=['POST'])
def verify_email():
    """Verify email with code"""
    try:
        data = request.json
        email = data.get('email')
        code = data.get('code')
        
        if not email or not code:
            return jsonify({'error': 'Email and verification code are required'}), 400
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.is_email_verified:
            return jsonify({'message': 'Email already verified'}), 200
        
        # Find latest unexpired token for user
        token = EmailVerificationToken.query.filter_by(
            user_id=user.id
        ).filter(
            EmailVerificationToken.consumed_at.is_(None)
        ).order_by(
            EmailVerificationToken.created_at.desc()
        ).first()
        
        if not token:
            return jsonify({'error': 'No verification code found. Please request a new one.'}), 400
        
        # Track attempt
        token.attempt_count += 1
        token.last_attempt_at = datetime.datetime.now()
        
        # Check max attempts (5)
        if token.attempt_count > 5:
            db.session.commit()
            return jsonify({'error': 'Too many attempts. Please request a new code.'}), 429
        
        if token.is_expired():
            db.session.commit()
            return jsonify({'error': 'Verification code expired. Please request a new one.'}), 400
        
        if not token.verify_code(code):
            db.session.commit()
            return jsonify({'error': 'Invalid verification code'}), 400
        
        # Mark token as consumed and user as verified
        token.consumed_at = datetime.datetime.now()
        user.is_email_verified = True
        user.email_verified_at = datetime.datetime.now()
        db.session.commit()
        
        # Log the user in
        login_user(user, remember=True)
        session.permanent = True
        
        return jsonify({
            'message': 'Email verified successfully!',
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'profile_image_url': user.profile_image_url or ''
            }
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Verify email error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification code with rate limiting"""
    try:
        data = request.json
        email = data.get('email')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.is_email_verified:
            return jsonify({'message': 'Email already verified'}), 200
        
        # Check cooldown (60 seconds)
        last_token = EmailVerificationToken.query.filter_by(
            user_id=user.id
        ).order_by(
            EmailVerificationToken.created_at.desc()
        ).first()
        
        if last_token:
            time_since_last = datetime.datetime.now() - last_token.created_at
            if time_since_last.total_seconds() < 60:
                remaining = 60 - int(time_since_last.total_seconds())
                return jsonify({
                    'error': f'Please wait {remaining} seconds before requesting a new code',
                    'cooldown': remaining
                }), 429
        
        # Create new token
        token, code = EmailVerificationToken.create_for_user(user.id)
        db.session.add(token)
        db.session.commit()
        
        email_sent = send_verification_email(email, code, user.first_name)
        
        return jsonify({
            'message': 'Verification code sent!',
            'email_sent': email_sent
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Resend verification error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout_replit():
    """Replit database logout endpoint"""
    try:
        from flask_login import logout_user as flask_logout_user
        flask_logout_user()
        return jsonify({'message': 'Logged out successfully'})
    except Exception as e:
        logging.error(f"Logout error: {e}")
        return jsonify({'error': str(e)}), 500

from flask import send_from_directory

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    full_path = os.path.join(FRONTEND_BUILD_DIR, path)
    if path != "" and os.path.exists(full_path) and not os.path.isdir(full_path):
        return send_from_directory(FRONTEND_BUILD_DIR, path)
    return send_from_directory(FRONTEND_BUILD_DIR, 'index.html')

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)

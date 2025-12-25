from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib
import secrets

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=True)
    password_hash = db.Column(db.String, nullable=True)  # For email/password auth
    first_name = db.Column(db.String, nullable=True)
    last_name = db.Column(db.String, nullable=True)
    profile_image_url = db.Column(db.String, nullable=True)
    is_email_verified = db.Column(db.Boolean, default=False)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def set_password(self, password):
        """Hash and store password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches stored hash"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class OAuth(OAuthConsumerMixin, db.Model):
    __tablename__ = 'oauth'
    user_id = db.Column(db.String, db.ForeignKey(User.id))
    browser_session_key = db.Column(db.String, nullable=False)
    user = db.relationship(User)

    __table_args__ = (UniqueConstraint(
        'user_id',
        'browser_session_key',
        'provider',
        name='uq_user_browser_session_key_provider',
    ),)


class EmailVerificationToken(db.Model):
    __tablename__ = 'email_verification_tokens'
    id = db.Column(db.String, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey(User.id), nullable=False)
    code_hash = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    attempt_count = db.Column(db.Integer, default=0)
    last_attempt_at = db.Column(db.DateTime, nullable=True)
    
    user = db.relationship(User, backref='verification_tokens')
    
    @staticmethod
    def hash_code(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()
    
    @staticmethod
    def generate_code() -> str:
        return ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    @classmethod
    def create_for_user(cls, user_id: str, expiry_minutes: int = 15):
        import uuid
        code = cls.generate_code()
        token = cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            code_hash=cls.hash_code(code),
            expires_at=datetime.now() + timedelta(minutes=expiry_minutes)
        )
        return token, code
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    def is_consumed(self) -> bool:
        return self.consumed_at is not None
    
    def verify_code(self, code: str) -> bool:
        return self.code_hash == self.hash_code(code)


class Notebook(db.Model):
    __tablename__ = 'notebooks'
    id = db.Column(db.String, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey(User.id), nullable=False)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)
    color = db.Column(db.String, default='#4285f4')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    user = db.relationship(User, backref='notebooks')
    documents = db.relationship('Document', backref='notebook', cascade='all, delete-orphan')
    chunks = db.relationship('Chunk', backref='notebook', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'color': self.color,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.String, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey(User.id), nullable=False)
    notebook_id = db.Column(db.String, db.ForeignKey('notebooks.id'), nullable=False)
    filename = db.Column(db.String, nullable=False)
    original_filename = db.Column(db.String, nullable=True)
    file_type = db.Column(db.String, nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    storage_path = db.Column(db.String, nullable=True)
    file_path = db.Column(db.String, nullable=True)
    processing_status = db.Column(db.String, default='pending')
    processing_error = db.Column(db.String, nullable=True)
    doc_metadata = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    user = db.relationship(User, backref='documents')
    chunks = db.relationship('Chunk', backref='document', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'notebook_id': self.notebook_id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'storage_path': self.storage_path,
            'file_path': self.file_path,
            'processing_status': self.processing_status,
            'processing_error': self.processing_error,
            'metadata': self.doc_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Chunk(db.Model):
    __tablename__ = 'chunks'
    id = db.Column(db.String, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey(User.id), nullable=False)
    notebook_id = db.Column(db.String, db.ForeignKey('notebooks.id'), nullable=False)
    document_id = db.Column(db.String, db.ForeignKey('documents.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    tokens = db.Column(db.Integer, nullable=True)
    embedding = db.Column(db.JSON, nullable=True)
    chunk_metadata = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    user = db.relationship(User, backref='chunks')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'notebook_id': self.notebook_id,
            'document_id': self.document_id,
            'content': self.content,
            'tokens': self.tokens,
            'embedding': self.embedding,
            'metadata': self.chunk_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

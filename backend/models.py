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

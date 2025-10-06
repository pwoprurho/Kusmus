from datetime import datetime
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import UserMixin, current_user
from kusmusapp import db, login_manager, bcrypt

@login_manager.user_loader
def load_user(user_id):
    """Required function for Flask-Login to load a user from the database."""
    from kusmusapp.models import User
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    """The User model for storing user accounts and their roles."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    
    streak = db.Column(db.Integer, default=1)
    study_reminder_time = db.Column(db.Time, nullable=True)
    daily_study_hours = db.Column(db.Float, nullable=True)

    courses = db.relationship('Course', backref='author', lazy=True)
    roadmaps = db.relationship('GeneratedRoadmap', backref='student', lazy=True, cascade="all, delete-orphan")
    
    def set_password(self, password_to_hash):
        self.password = bcrypt.generate_password_hash(password_to_hash).decode('utf-8')

    def check_password(self, password_to_check):
        return bcrypt.check_password_hash(self.password, password_to_check)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.role}')"

class GeneratedRoadmap(db.Model):
    """Stores the AI-generated roadmap for a user."""
    id = db.Column(db.Integer, primary_key=True)
    goal = db.Column(db.Text, nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    steps = db.relationship('RoadmapStep', backref='roadmap', lazy=True, cascade="all, delete-orphan")

class RoadmapStep(db.Model):
    """Stores a single step within a generated roadmap."""
    id = db.Column(db.Integer, primary_key=True)
    step_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='not_started')
    roadmap_id = db.Column(db.Integer, db.ForeignKey('generated_roadmap.id'), nullable=False)

class Course(db.Model):
    """The Course model for storing course information."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lessons = db.relationship('Lesson', backref='course', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"Course('{self.title}', '{self.date_posted}')"

class Lesson(db.Model):
    """The Lesson model, supporting multiple content types."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    lesson_type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(100), nullable=True) 
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)

    def __repr__(self):
        return f"Lesson('{self.title}', '{self.lesson_type}')"

# Association table for chat participants. Must be defined BEFORE the classes that use it.
chat_participants = db.Table('chat_participants',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('chat_session_id', db.Integer, db.ForeignKey('chat_session.id'), primary_key=True)
)

class ChatSession(db.Model):
    """A single chat session, either with the AI or between users."""
    id = db.Column(db.Integer, primary_key=True)
    session_name = db.Column(db.String(100), nullable=True)
    is_ai_chat = db.Column(db.Boolean, default=False)
    messages = db.relationship('ChatMessage', backref='session', lazy=True, cascade="all, delete-orphan")
    participants = db.relationship('User', secondary=chat_participants, lazy='subquery',
                                   backref=db.backref('chat_sessions', lazy=True))

class ChatMessage(db.Model):
    """A single message within a chat session."""
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sender = db.relationship('User')
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=False)

def admin_required(f):
    """A decorator to restrict access to a route to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function
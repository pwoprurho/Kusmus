"""
Models module - Lightweight data classes for Supabase.
No more SQLAlchemy. Uses the Supabase client for all DB operations.
Flask-Login integration uses a simple User class with UserMixin.
"""
import json
from datetime import datetime
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import UserMixin, current_user
from kusmusapp import login_manager, bcrypt
from kusmusapp.services.supabase_client import get_supabase


# --- Flask-Login User Loader ---
@login_manager.user_loader
def load_user(user_id):
    """Loads a user from Supabase by ID for Flask-Login."""
    try:
        sb = get_supabase()
        result = sb.table('users').select('*').eq('id', int(user_id)).single().execute()
        if result.data:
            return User.from_dict(result.data)
    except Exception:
        pass
    return None


# --- Data Classes ---

class User(UserMixin):
    """User data class compatible with Flask-Login."""
    def __init__(self, id=None, username='', email='', password='', role='student',
                 streak=1, study_reminder_time=None, daily_study_hours=None,
                  full_name='', phone_number='', state='', lga='', gender='', age=None, is_admin=False,
                  avatar_url=None, wallpaper_url=None):
        self.id = id
        self.username = username
        self.email = email
        self.password = password
        self.role = role
        self.streak = streak
        self.study_reminder_time = study_reminder_time
        self.daily_study_hours = daily_study_hours
        self.full_name = full_name
        self.phone_number = phone_number
        self.state = state
        self.lga = lga
        self.gender = gender
        self.age = age
        self.is_admin = is_admin
        self.avatar_url = avatar_url
        self.wallpaper_url = wallpaper_url

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get('id'),
            username=data.get('username', ''),
            email=data.get('email', ''),
            password=data.get('password', ''),
            role=data.get('role', 'student'),
            streak=data.get('streak', 1),
            study_reminder_time=data.get('study_reminder_time'),
            daily_study_hours=data.get('daily_study_hours'),
            full_name=data.get('full_name', ''),
            phone_number=data.get('phone_number', ''),
            state=data.get('state', ''),
            lga=data.get('lga', ''),
            gender=data.get('gender', ''),
            age=data.get('age'),
            is_admin=data.get('is_admin', False),
            avatar_url=data.get('avatar_url'),
            wallpaper_url=data.get('wallpaper_url'),
        )

    def set_password(self, password_to_hash):
        self.password = bcrypt.generate_password_hash(password_to_hash).decode('utf-8')

    def check_password(self, password_to_check):
        try:
            return bcrypt.check_password_hash(self.password, password_to_check)
        except ValueError:
            # This happens if the stored password is not a valid bcrypt hash (e.g., OAuth placeholder)
            return False

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.role}')"


# --- Helpers ---

def parse_date(date_data):
    """Parses a date string from Supabase or returns a datetime object."""
    if not date_data:
        return datetime.utcnow()
    if isinstance(date_data, datetime):
        return date_data
    try:
        # Handles standard Postgres/Supabase ISO strings with Z
        return datetime.fromisoformat(date_data.replace('Z', '+00:00'))
    except Exception:
        return datetime.utcnow()


class GeneratedRoadmap:
    """Roadmap data class."""
    def __init__(self, id=None, goal='', content='', image_url=None,
                 date_created=None, user_id=None, steps=None):
        self.id = id
        self.goal = goal
        self.content = content
        self.image_url = image_url
        self.date_created = parse_date(date_created)
        self.user_id = user_id
        self.steps = steps or []

    @classmethod
    def from_dict(cls, data, steps=None):
        return cls(
            id=data.get('id'),
            goal=data.get('goal', ''),
            content=data.get('content', ''),
            image_url=data.get('image_url'),
            date_created=data.get('date_created'),
            user_id=data.get('user_id'),
            steps=steps or [],
        )


class RoadmapStep:
    """Step data class."""
    def __init__(self, id=None, step_number=0, title='', description='',
                 youtube_queries=None, lecture_content=None, audio_url=None,
                 status='not_started', roadmap_id=None):
        self.id = id
        self.step_number = step_number
        self.title = title
        self.description = description
        self.youtube_queries = youtube_queries
        self.lecture_content = lecture_content
        self.audio_url = audio_url
        self.status = status
        self.roadmap_id = roadmap_id

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get('id'),
            step_number=data.get('step_number', 0),
            title=data.get('title', ''),
            description=data.get('description', ''),
            youtube_queries=data.get('youtube_queries'),
            lecture_content=data.get('lecture_content'),
            audio_url=data.get('audio_url'),
            status=data.get('status', 'not_started'),
            roadmap_id=data.get('roadmap_id'),
        )

    def get_queries(self):
        if not self.youtube_queries:
            return []
        try:
            return json.loads(self.youtube_queries)
        except Exception:
            return []


class Course:
    """Course data class."""
    def __init__(self, id=None, title='', description='', author_id=None, 
                 date_posted=None, author=None, lessons=None):
        self.id = id
        self.title = title
        self.description = description
        self.author_id = author_id
        self.date_posted = parse_date(date_posted)
        self.author = author
        self.lessons = lessons or []

    @classmethod
    def from_dict(cls, data, author=None, lessons=None):
        return cls(
            id=data.get('id'),
            title=data.get('title', ''),
            description=data.get('description', ''),
            author_id=data.get('author_id'),
            date_posted=data.get('date_posted'),
            author=author,
            lessons=lessons or []
        )


class Lesson:
    """Lesson data class."""
    def __init__(self, id=None, course_id=None, title='', content='', 
                 file_path='', lesson_type='text', date_posted=None):
        self.id = id
        self.course_id = course_id
        self.title = title
        self.content = content
        self.file_path = file_path
        self.lesson_type = lesson_type
        self.date_posted = parse_date(date_posted)

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get('id'),
            course_id=data.get('course_id'),
            title=data.get('title', ''),
            content=data.get('content', ''),
            file_path=data.get('file_path', ''),
            lesson_type=data.get('lesson_type', 'text'),
            date_posted=data.get('date_posted')
        )


# --- Decorators ---

def admin_required(f):
    """Restricts access to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role != 'admin' and not current_user.is_admin):
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function

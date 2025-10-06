import os
import secrets
import re
from urllib.parse import urlparse, parse_qs
import google.generativeai as genai
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory, abort, session
from flask_login import login_user, current_user, logout_user, login_required
from kusmusapp import db
from kusmusapp.models import User, Course, Lesson, GeneratedRoadmap, RoadmapStep, admin_required
from kusmusapp.forms import (RegistrationForm, LoginForm, CourseForm, 
                           TextLessonForm, FileLessonForm, VideoLessonForm, YouTubeLessonForm, OnboardingForm)

main = Blueprint('main', __name__)

def save_lesson_file(form_file_data, subfolder):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_file_data.filename)
    file_fn = random_hex + f_ext
    file_path = os.path.join(current_app.root_path, f'uploads/{subfolder}', file_fn)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    form_file_data.save(file_path)
    return file_fn

def get_youtube_id(url):
    if url is None: return None
    query = urlparse(url)
    if query.hostname == 'youtu.be': return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p.get('v', [None])[0]
        if query.path[:7] == '/embed/': return query.path.split('/')[2]
        if query.path[:3] == '/v/': return query.path.split('/')[2]
    return None

# --- AUTHENTICATION ROUTES ---
@main.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('main.home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        new_user = User(username=form.username.data, email=form.email.data)
        new_user.set_password(form.password.data)
        db.session.add(new_user)
        db.session.commit()
        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html', title='Register', form=form)

@main.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash('Login successful!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        else:
            flash('Login failed. Please check your email and password.', 'danger')
    return render_template('login.html', title='Login', form=form)

@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))

# --- MAIN WEBSITE ROUTES ---
@main.route('/')
def home():
    return render_template('index.html')

@main.route('/about')
def about():
    return render_template('about.html', title='About Us')

@main.route('/team')
def team():
    return render_template('team.html', title='Our Team')

@main.route('/consult')
def consult():
    return render_template('consult.html', title='Consultation')

@main.route('/academy')
def academy_landing():
    return render_template('academy_landing.html', title='Kusmus Academy')

# --- UNIFIED DASHBOARD & ONBOARDING ---
@main.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        courses = Course.query.order_by(Course.date_posted.desc()).all()
        return render_template('admin/admin_dashboard.html', title='Admin Dashboard', courses=courses)
    
    elif current_user.role == 'student':
        user_roadmap = GeneratedRoadmap.query.filter_by(student=current_user).first()
        return render_template('student/student_dashboard.html', title='My Dashboard', roadmap=user_roadmap)
        
    else:
        return redirect(url_for('main.home'))

@main.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    form = OnboardingForm()
    if form.validate_on_submit():
        ambition = form.ambition.data
        hours = form.study_hours.data
        remind_time = form.reminder_time.data
        current_user.daily_study_hours = hours
        current_user.study_reminder_time = remind_time
        db.session.commit()
        try:
            API_KEY = os.getenv('GEMINI_API_KEY')
            if not API_KEY:
                flash('GEMINI_API_KEY not found. Please set it in your .env file.', 'danger')
                return render_template('student/onboarding.html', title='Create Your Path', form=form)
            
            genai.configure(api_key=API_KEY)
            
            text_model = genai.GenerativeModel('gemini-2.5-flash-lite-latest')
            text_prompt = f"""Generate a 7-step learning roadmap for a user who wants to '{ambition}'. The user can study for {hours} hours a day. Format the output strictly as a numbered list. Each item must start with 'Step X:'. Each step must have a title and a one-sentence description. Example: Step 1: Title of Step 1. A brief description of this step."""
            text_response = text_model.generate_content(text_prompt)
            roadmap_text = text_response.text

            banner_model = genai.GenerativeModel('gemini-2.5-flash-lite-latest')
            banner_prompt = f"Generate a visually appealing, abstract, motivational banner image for a '{ambition}' tech career roadmap. Style: digital art, futuristic, clean, vibrant colors."
            banner_response = banner_model.generate_content(banner_prompt, generation_config={"response_mime_type": "image/png"})
            banner_image_url = banner_response.candidates[0].content.parts[0].uri
            
            new_roadmap = GeneratedRoadmap(goal=ambition, content=roadmap_text, image_url=banner_image_url, student=current_user)
            db.session.add(new_roadmap)
            db.session.commit()
            
            steps = re.findall(r"Step (\d+): (.*?)\. (.*?)(?=\nStep|\Z)", roadmap_text, re.DOTALL)
            for step in steps:
                step_number, title, description = step
                new_step = RoadmapStep(step_number=int(step_number), title=title.strip(), description=description.strip(), roadmap=new_roadmap)
                db.session.add(new_step)
            db.session.commit()

            flash('Your personalized roadmap has been generated!', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            flash(f'An error occurred with the AI. Please try again. Error: {e}', 'danger')
    return render_template('student/onboarding.html', title='Create Your Path', form=form)


@main.route('/onboarding/success')
@login_required
def onboarding_success():
    return render_template('student/onboarding_success.html', title='Roadmap Generated!')

# --- ADMIN & CONTENT MANAGEMENT ROUTES ---
@main.route('/ai-tutor')
@login_required
def ai_tutor():
    return render_template('student/ai_tutor.html', title='AI Tutor')

@main.route("/admin/course/new", methods=['GET', 'POST'])
@login_required
@admin_required
def create_course():
    form = CourseForm()
    if form.validate_on_submit():
        course = Course(title=form.title.data, description=form.description.data, author=current_user)
        db.session.add(course)
        db.session.commit()
        flash('Your course has been created!', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('admin/create_course.html', title='New Course', form=form, legend='Create a New Course')

@main.route("/course/<int:course_id>")
@login_required
@admin_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template('admin/course_detail.html', title=course.title, course=course)

@main.route("/course/<int:course_id>/update", methods=['GET', 'POST'])
@login_required
@admin_required
def update_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.author != current_user and current_user.role != 'admin':
        abort(403)
    form = CourseForm()
    if form.validate_on_submit():
        course.title = form.title.data
        course.description = form.description.data
        db.session.commit()
        flash('Your course has been updated!', 'success')
        return redirect(url_for('main.dashboard'))
    elif request.method == 'GET':
        form.title.data = course.title
        form.description.data = course.description
    return render_template('admin/create_course.html', title='Update Course', form=form, legend='Update Course')

@main.route("/course/<int:course_id>/delete", methods=['POST'])
@login_required
@admin_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.author != current_user and current_user.role != 'admin':
        abort(403)
    db.session.delete(course)
    db.session.commit()
    flash('The course has been deleted!', 'success')
    return redirect(url_for('main.dashboard'))

# Lesson CRUD
@main.route("/course/<int:course_id>/add_text_lesson", methods=['GET', 'POST'])
@login_required
@admin_required
def add_text_lesson(course_id):
    course = Course.query.get_or_404(course_id)
    form = TextLessonForm()
    if form.validate_on_submit():
        lesson = Lesson(title=form.title.data, content=form.content.data, lesson_type='text', course=course)
        db.session.add(lesson)
        db.session.commit()
        flash('Your text lesson has been added!', 'success')
        return redirect(url_for('main.course_detail', course_id=course.id))
    return render_template('admin/create_lesson_text.html', title='New Text Lesson', form=form, course=course)

@main.route("/course/<int:course_id>/add_file_lesson", methods=['GET', 'POST'])
@login_required
@admin_required
def add_file_lesson(course_id):
    course = Course.query.get_or_404(course_id)
    form = FileLessonForm()
    if form.validate_on_submit():
        filename = save_lesson_file(form.document.data, 'lessons/docs')
        lesson = Lesson(title=form.title.data, file_path=filename, lesson_type='file', course=course)
        db.session.add(lesson)
        db.session.commit()
        flash('Your file lesson has been uploaded!', 'success')
        return redirect(url_for('main.course_detail', course_id=course.id))
    return render_template('admin/create_lesson_file.html', title='New File Lesson', form=form, course=course)

@main.route("/course/<int:course_id>/add_video_lesson", methods=['GET', 'POST'])
@login_required
@admin_required
def add_video_lesson(course_id):
    course = Course.query.get_or_404(course_id)
    form = VideoLessonForm()
    if form.validate_on_submit():
        filename = save_lesson_file(form.video.data, 'lessons/videos')
        lesson = Lesson(title=form.title.data, file_path=filename, lesson_type='video', course=course)
        db.session.add(lesson)
        db.session.commit()
        flash('Your video lesson has been uploaded!', 'success')
        return redirect(url_for('main.course_detail', course_id=course.id))
    return render_template('admin/create_lesson_video.html', title='New Video Lesson', form=form, course=course)

@main.route("/course/<int:course_id>/add_youtube_lesson", methods=['GET', 'POST'])
@login_required
@admin_required
def add_youtube_lesson(course_id):
    course = Course.query.get_or_404(course_id)
    form = YouTubeLessonForm()
    if form.validate_on_submit():
        video_id = get_youtube_id(form.youtube_url.data)
        if video_id:
            lesson = Lesson(title=form.title.data, file_path=video_id, lesson_type='youtube', course=course)
            db.session.add(lesson)
            db.session.commit()
            flash('Your YouTube lesson has been added!', 'success')
            return redirect(url_for('main.course_detail', course_id=course.id))
        else:
            flash('Invalid YouTube URL. Please try again.', 'danger')
    return render_template('admin/create_lesson_youtube.html', title='New YouTube Lesson', form=form, course=course)

@main.route("/lesson/<int:lesson_id>/update", methods=['GET', 'POST'])
@login_required
@admin_required
def update_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    if lesson.lesson_type == 'text':
        form = TextLessonForm()
        template = 'admin/create_lesson_text.html'
    elif lesson.lesson_type == 'youtube':
        form = YouTubeLessonForm()
        template = 'admin/create_lesson_youtube.html'
    else:
        form = TextLessonForm()
        del form.content
        template = 'admin/update_lesson_file.html'
    if form.validate_on_submit():
        lesson.title = form.title.data
        if lesson.lesson_type == 'text':
            lesson.content = form.content.data
        elif lesson.lesson_type == 'youtube':
            video_id = get_youtube_id(form.youtube_url.data)
            if video_id:
                lesson.file_path = video_id
            else:
                flash('Invalid YouTube URL.', 'danger')
        db.session.commit()
        flash('Your lesson has been updated!', 'success')
        return redirect(url_for('main.course_detail', course_id=lesson.course_id))
    elif request.method == 'GET':
        form.title.data = lesson.title
        if lesson.lesson_type == 'text':
            form.content.data = lesson.content
        elif lesson.lesson_type == 'youtube':
            form.youtube_url.data = f'https://www.youtube.com/watch?v={lesson.file_path}'
    return render_template(template, title='Update Lesson', form=form, legend=f'Update {lesson.title}', lesson=lesson)

@main.route("/lesson/<int:lesson_id>/delete", methods=['POST'])
@login_required
@admin_required
def delete_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    course_id = lesson.course_id
    if lesson.lesson_type in ['file', 'video']:
        subfolder = 'lessons/docs' if lesson.lesson_type == 'file' else 'lessons/videos'
        file_to_delete = os.path.join(current_app.root_path, f'uploads/{subfolder}', lesson.file_path)
        if os.path.exists(file_to_delete):
            os.remove(file_to_delete)
    db.session.delete(lesson)
    db.session.commit()
    flash('The lesson has been deleted!', 'success')
    return redirect(url_for('main.course_detail', course_id=course_id))

@main.route("/lesson/<int:lesson_id>")
@login_required
def view_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    return render_template('admin/view_lesson.html', title=lesson.title, lesson=lesson)

@main.route('/uploads/<path:subfolder>/<path:filename>')
@login_required
def uploaded_file(subfolder, filename):
    return send_from_directory(os.path.join(current_app.root_path, f'uploads/{subfolder}'), filename)
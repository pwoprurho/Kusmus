import os
import json
import secrets
from collections import Counter
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app, send_from_directory, abort, Response, session, jsonify)
from flask_login import login_user, current_user, logout_user, login_required
from kusmusapp import bcrypt
from kusmusapp.models import User, GeneratedRoadmap, RoadmapStep, Course, Lesson, admin_required
from kusmusapp.forms import (RegistrationForm, LoginForm, OnboardingForm, CourseForm, 
                            TextLessonForm, FileLessonForm, VideoLessonForm, YouTubeLessonForm)
from kusmusapp.services.supabase_client import get_supabase
from kusmusapp.services.ai_service import AIService
from kusmusapp.services.calendar_service import CalendarService
from kusmusapp.services.google_calendar_service import GoogleCalendarService

import logging
logger = logging.getLogger(__name__)

main = Blueprint('main', __name__)

# ============================================================
# AUTHENTICATION ROUTES
# ============================================================

@main.route("/login/oauth/<provider>")
def login_oauth(provider):
    """Start Supabase OAuth flow for login/registration."""
    sb = get_supabase()
    redirect_url = url_for('main.oauth_callback', _external=True)
    res = sb.auth.sign_in_with_oauth({
        "provider": provider,
        "options": {
            "token_refresh_hint": "refresh",
            "redirect_to": redirect_url
        }
    })
    return redirect(res.url)


@main.route("/link/oauth/<provider>")
@login_required
def link_oauth(provider):
    """Start Supabase OAuth flow with intent to link to current account."""
    sb = get_supabase()
    # We can use the same callback, but the callback will check if current_user is auth'd
    redirect_url = url_for('main.oauth_callback', _external=True)
    res = sb.auth.sign_in_with_oauth({
        "provider": provider,
        "options": {
            "redirect_to": redirect_url
        }
    })
    return redirect(res.url)


@main.route("/auth/callback")
def oauth_callback():
    """Handle Supabase OAuth callback."""
    sb = get_supabase()
    # In some cases, we might need to get the session from the URL query
    # but Supabase client handles it if we are on the same domain/session.
    try:
        user_res = sb.auth.get_user()
        if user_res and user_res.user:
            email = user_res.user.email
            
            # If user is already logged in, we are LINKING
            if current_user.is_authenticated:
                if current_user.email != email:
                    flash(f'Note: The social account email ({email}) is different from your current account email ({current_user.email}). Linking anyway...', 'info')
                
                # Update the existing user record if necessary (e.g., adding a provider flag)
                # For now, we just acknowledge the link via Supabase Auth's internal handling
                flash('Social account linked successfully!', 'success')
                return redirect(url_for('main.dashboard'))

            # Otherwise, we are LOGGING IN / REGISTERING
            res = sb.table('users').select('*').eq('email', email).execute()
            if res.data:
                user = User.from_dict(res.data[0])
            else:
                # Create user if they don't exist (Registration)
                username = email.split('@')[0]
                res = sb.table('users').insert({
                    'email': email,
                    'username': username,
                    'password': secrets.token_urlsafe(16),
                    'role': 'student',
                    'streak': 1
                }).execute()
                user = User.from_dict(res.data[0])
            
            login_user(user)
            flash('Logged in successfully via Social Login!', 'success')
            return redirect(url_for('main.dashboard'))
    except Exception as e:
        logger.error(f"OAuth Callback Error: {e}")
    
    # If no session yet, we might be in the middle of a fragment redirect.
    return render_template('auth_callback.html')


@main.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    form = RegistrationForm()
    
    # Load location data for the dropdowns
    location_path = os.path.join(current_app.root_path, '..', 'location.json')
    try:
        with open(location_path, 'r') as f:
            location_data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading location.json: {e}")
        location_data = {"locations": []}

    # Populate state choices
    states = [('', 'Select State')] + [(loc['state'], loc['state'].title()) for loc in location_data['locations']]
    form.state.choices = states
    
    # LGA choices (will be updated via JS, but we need valid choices for validation)
    if form.state.data:
        selected_state = form.state.data
        lgas = next((loc['localGovt'] for loc in location_data['locations'] if loc['state'] == selected_state), [])
        form.lga.choices = [('', 'Select LGA')] + [(lga, lga.title()) for lga in lgas]
    else:
        form.lga.choices = [('', 'Select LGA')]

    if form.validate_on_submit():
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        sb = get_supabase()
        try:
            sb.table('users').insert({
                'full_name': form.full_name.data,
                'username': form.username.data,
                'email': form.email.data,
                'phone_number': form.phone_number.data,
                'password': hashed_pw,
                'state': form.state.data,
                'lga': form.lga.data,
                'gender': form.gender.data,
                'age': form.age.data,
                'role': 'student',
                'streak': 1,
            }).execute()
            flash('Your account has been created! You can now log in.', 'success')
            return redirect(url_for('main.login'))
        except Exception as e:
            logger.error(f"Registration DB Error: {e}")
            flash('An error occurred during registration. Please check the console.', 'danger')

    return render_template('register.html', title='Register', form=form, location_json=json.dumps(location_data))


@main.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        sb = get_supabase()
        result = sb.table('users').select('*').eq('email', form.email.data).execute()
        if result.data:
            user = User.from_dict(result.data[0])
            if user.check_password(form.password.data):
                login_user(user, remember=form.remember.data)
                next_page = request.args.get('next')
                flash('Login successful!', 'success')
                return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        flash('Login failed. Please check your email and password.', 'danger')
    return render_template('login.html', title='Login', form=form)


@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))


# ============================================================
# MAIN WEBSITE ROUTES
# ============================================================

@main.route('/')
def home():
    # Home now shows the Academy Landing content
    return academy_landing()

@main.route('/about')
def about():
    # About now shows the former index.html content
    return render_template('index.html', title='About ADC Academy')

@main.route('/team')
def team():
    return render_template('team.html', title='Our Team')

@main.route('/consult')
def consult():
    return render_template('consult.html', title='Consultation')

@main.route('/academy')
def academy_landing():
    sb = get_supabase()
    try:
        # Total students
        students_res = sb.table('users').select('id, username, streak').eq('role', 'student').execute()
        total_students = len(students_res.data) if students_res.data else 0
        # Total courses
        courses_res = sb.table('courses').select('id').execute()
        total_courses = len(courses_res.data) if courses_res.data else 0
        # Top active students (by streak, top 5)
        top_students = []
        if students_res.data:
            sorted_students = sorted(students_res.data, key=lambda x: x.get('streak', 0) or 0, reverse=True)[:5]
            top_students = [{'username': s['username'], 'streak': s.get('streak', 0) or 0} for s in sorted_students]
    except Exception as e:
        logger.error(f'Homepage stats error: {e}')
        total_students, total_courses, top_students = 0, 0, []
    return render_template('academy_landing.html', title='ADC Academy',
                           total_students=total_students, total_courses=total_courses,
                           top_students=top_students)


# ============================================================
# DASHBOARD & ONBOARDING (Student-Driven)
# ============================================================

@main.route("/admin/dashboard")
@admin_required
def admin_dashboard_redirect():
    return redirect(url_for('main.dashboard'))


@main.route('/admin/api/analytics')
@login_required
def admin_analytics_api():
    """JSON API for admin dashboard charts and map."""
    sb = get_supabase()
    try:
        students_res = sb.table('users').select('state, lga, age').eq('role', 'student').execute()
        students = students_res.data or []

        # --- Map Data: students per state ---
        state_counts = Counter(s.get('state') or 'Unknown' for s in students if s.get('state'))
        map_data = dict(state_counts)

        # --- LGA Bar Chart ---
        lga_counts = Counter(s.get('lga') or 'Unknown' for s in students if s.get('lga'))
        lga_sorted = lga_counts.most_common(15)
        lga_chart = {'labels': [x[0] for x in lga_sorted], 'data': [x[1] for x in lga_sorted]}

        # --- Skills by Age Pie Chart ---
        roadmaps_res = sb.table('generated_roadmaps').select('user_id, goal').execute()
        roadmaps = roadmaps_res.data or []
        user_age_map = {s.get('id'): s.get('age') for s in (sb.table('users').select('id, age').eq('role', 'student').execute().data or [])}

        age_buckets = {'15-20': 0, '21-25': 0, '26-30': 0, '31+': 0}
        for r in roadmaps:
            age = user_age_map.get(r.get('user_id'))
            if age:
                if 15 <= age <= 20: age_buckets['15-20'] += 1
                elif 21 <= age <= 25: age_buckets['21-25'] += 1
                elif 26 <= age <= 30: age_buckets['26-30'] += 1
                else: age_buckets['31+'] += 1

        skills_chart = {'labels': list(age_buckets.keys()), 'data': list(age_buckets.values())}

        # --- Stats ---
        courses_count = len(sb.table('courses').select('id').execute().data or [])
        unique_lgas = len(set(s.get('lga') for s in students if s.get('lga')))

        return jsonify({
            'stats': {'total_students': len(students), 'total_courses': courses_count, 'total_lgas': unique_lgas},
            'map_data': map_data,
            'lga_chart': lga_chart,
            'skills_by_age': skills_chart
        })
    except Exception as e:
        logger.error(f'Analytics API Error: {e}')
        return jsonify({'stats': {}, 'map_data': {}, 'lga_chart': {'labels': [], 'data': []}, 'skills_by_age': {'labels': [], 'data': []}})


@main.route('/admin/students')
@login_required
def admin_students():
    """Dedicated page for viewing all registered students."""
    sb = get_supabase()
    students_res = sb.table('users').select('*').eq('role', 'student').execute()
    students = [User.from_dict(s) for s in students_res.data] if students_res.data else []
    return render_template('admin/students_list.html', title='Registered Students', students=students)


@main.route('/dashboard')
@login_required
def dashboard():
    sb = get_supabase()

    if current_user.role == 'admin':
        students_res = sb.table('users').select('id').eq('role', 'student').execute()
        total_students = len(students_res.data) if students_res.data else 0
        courses_res = sb.table('courses').select('id').execute()
        total_courses = len(courses_res.data) if courses_res.data else 0
        return render_template('admin/admin_dashboard.html', title='Admin Dashboard',
                               total_students=total_students, total_courses=total_courses)

    # Student dashboard
    # --- Daily Streak Logic ---
    today = datetime.utcnow().date()
    # current_user.last_activity_date is a string from Supabase ('YYYY-MM-DD')
    last_date = None
    if current_user.last_activity_date:
        if isinstance(current_user.last_activity_date, str):
            last_date = datetime.strptime(current_user.last_activity_date, '%Y-%m-%d').date()
        else:
            last_date = current_user.last_activity_date

    if not last_date:
        # First visit or old user without date
        current_user.streak = 1
        current_user.last_activity_date = today
        sb.table('users').update({'streak': 1, 'last_activity_date': today.isoformat()}).eq('id', current_user.id).execute()
    elif last_date < today:
        if last_date == today - timedelta(days=1):
            # Consecutive day!
            current_user.streak += 1
        else:
            # Missed a day or more
            current_user.streak = 1
        
        current_user.last_activity_date = today
        sb.table('users').update({
            'streak': current_user.streak, 
            'last_activity_date': today.isoformat()
        }).eq('id', current_user.id).execute()
    # If last_date == today, we do nothing (already updated today)

    roadmap = None
    result = sb.table('generated_roadmaps').select('*').eq('user_id', current_user.id).order('date_created', desc=True).limit(1).execute()
    if result.data:
        roadmap_data = result.data[0]
        # Fetch steps for this roadmap
        steps_result = sb.table('roadmap_steps').select('*').eq('roadmap_id', roadmap_data['id']).order('step_number').execute()
        steps = [RoadmapStep.from_dict(s) for s in steps_result.data] if steps_result.data else []
        roadmap = GeneratedRoadmap.from_dict(roadmap_data, steps=steps)

    return render_template('student/student_dashboard.html', title='My Dashboard', roadmap=roadmap)


@main.route("/academy/community")
@login_required
def community():
    sb = get_supabase()
    
    # 1. Get current user's roadmap goal
    roadmap_res = sb.table('generated_roadmaps').select('goal').eq('user_id', current_user.id).order('date_created', desc=True).limit(1).execute()
    
    peers = []
    my_goal = None
    if roadmap_res.data:
        my_goal = roadmap_res.data[0]['goal']
        goal_keywords = [w.lower() for w in my_goal.split() if len(w) > 3]
        
        # 2. Find other roadmaps (recent 50) and filter for similarity
        all_roadmaps_res = sb.table('generated_roadmaps').select('*, users(*)').neq('user_id', current_user.id).order('date_created', desc=True).limit(50).execute()
        
        if all_roadmaps_res.data:
            for r in all_roadmaps_res.data:
                other_goal = r['goal'].lower()
                if any(kw in other_goal for kw in goal_keywords):
                    user_data = r.get('users')
                    if user_data:
                        peers.append({
                            'user': User.from_dict(user_data),
                            'goal': r['goal']
                        })

    return render_template('student/academy_community.html', title='Academy Community', peers=peers, my_goal=my_goal)


@main.route("/admin/course/new", methods=['GET', 'POST'])
@admin_required
def create_course():
    form = CourseForm()
    if form.validate_on_submit():
        sb = get_supabase()
        try:
            sb.table('courses').insert({
                'title': form.title.data,
                'description': form.description.data,
                'author_id': current_user.id
            }).execute()
            flash('Course created successfully!', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            logger.error(f"Error creating course: {e}")
            flash('Error creating course.', 'danger')
    return render_template('admin/create_course.html', title='New Course', form=form, legend='New Course')


@main.route("/admin/course/<int:course_id>")
@admin_required
def course_detail(course_id):
    sb = get_supabase()
    # Fetch course
    course_res = sb.table('courses').select('*').eq('id', course_id).single().execute()
    if not course_res.data:
        abort(404)
    
    # Fetch lessons
    lessons_res = sb.table('lessons').select('*').eq('course_id', course_id).order('date_posted').execute()
    lessons = [Lesson.from_dict(l) for l in lessons_res.data] if lessons_res.data else []
    
    course = Course.from_dict(course_res.data, lessons=lessons)
    return render_template('admin/course_detail.html', title=course.title, course=course)


@main.route("/admin/course/<int:course_id>/update", methods=['GET', 'POST'])
@admin_required
def update_course(course_id):
    sb = get_supabase()
    course_res = sb.table('courses').select('*').eq('id', course_id).single().execute()
    if not course_res.data:
        abort(404)
    
    form = CourseForm()
    if form.validate_on_submit():
        try:
            sb.table('courses').update({
                'title': form.title.data,
                'description': form.description.data
            }).eq('id', course_id).execute()
            flash('Course updated successfully!', 'success')
            return redirect(url_for('main.course_detail', course_id=course_id))
        except Exception as e:
            logger.error(f"Error updating course: {e}")
            flash('Error updating course.', 'danger')
    elif request.method == 'GET':
        form.title.data = course_res.data['title']
        form.description.data = course_res.data['description']
    
    return render_template('admin/create_course.html', title='Update Course', form=form, legend='Update Course')


@main.route("/admin/course/<int:course_id>/delete", methods=['POST'])
@admin_required
def delete_course(course_id):
    sb = get_supabase()
    try:
        sb.table('courses').delete().eq('id', course_id).execute()
        flash('Course deleted successfully!', 'success')
    except Exception as e:
        logger.error(f"Error deleting course: {e}")
        flash('Error deleting course.', 'danger')
    return redirect(url_for('main.dashboard'))


def save_file(form_file, subfolder):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_file.filename)
    filename = random_hex + f_ext
    
    upload_path = os.path.join(current_app.root_path, 'uploads', subfolder)
    if not os.path.exists(upload_path):
        os.makedirs(upload_path, exist_ok=True)
        
    form_file.save(os.path.join(upload_path, filename))
    return filename


@main.route("/admin/course/<int:course_id>/lesson/text", methods=['GET', 'POST'])
@admin_required
def add_text_lesson(course_id):
    sb = get_supabase()
    course_res = sb.table('courses').select('*').eq('id', course_id).single().execute()
    if not course_res.data:
        abort(404)
    
    form = TextLessonForm()
    if form.validate_on_submit():
        sb.table('lessons').insert({
            'course_id': course_id,
            'title': form.title.data,
            'content': form.content.data,
            'lesson_type': 'text'
        }).execute()
        flash('Lesson added!', 'success')
        return redirect(url_for('main.course_detail', course_id=course_id))
    return render_template('admin/create_lesson_text.html', title='Add Text Lesson', form=form, course=course_res.data)


@main.route("/admin/course/<int:course_id>/lesson/file", methods=['GET', 'POST'])
@admin_required
def add_file_lesson(course_id):
    sb = get_supabase()
    course_res = sb.table('courses').select('*').eq('id', course_id).single().execute()
    if not course_res.data:
        abort(404)
    
    form = FileLessonForm()
    if form.validate_on_submit():
        filename = save_file(form.file.data, 'lessons/docs')
        sb.table('lessons').insert({
            'course_id': course_id,
            'title': form.title.data,
            'file_path': filename,
            'lesson_type': 'file'
        }).execute()
        flash('File lesson added!', 'success')
        return redirect(url_for('main.course_detail', course_id=course_id))
    return render_template('admin/create_lesson_file.html', title='Add File Lesson', form=form, course=course_res.data)


@main.route("/admin/course/<int:course_id>/lesson/video", methods=['GET', 'POST'])
@admin_required
def add_video_lesson(course_id):
    sb = get_supabase()
    course_res = sb.table('courses').select('*').eq('id', course_id).single().execute()
    if not course_res.data:
        abort(404)
    
    form = VideoLessonForm()
    if form.validate_on_submit():
        filename = save_file(form.video.data, 'lessons/videos')
        sb.table('lessons').insert({
            'course_id': course_id,
            'title': form.title.data,
            'file_path': filename,
            'lesson_type': 'video'
        }).execute()
        flash('Video lesson added!', 'success')
        return redirect(url_for('main.course_detail', course_id=course_id))
    return render_template('admin/create_lesson_video.html', title='Add Video Lesson', form=form, course=course_res.data)


@main.route("/admin/course/<int:course_id>/lesson/youtube", methods=['GET', 'POST'])
@admin_required
def add_youtube_lesson(course_id):
    sb = get_supabase()
    course_res = sb.table('courses').select('*').eq('id', course_id).single().execute()
    if not course_res.data:
        abort(404)
    
    form = YouTubeLessonForm()
    if form.validate_on_submit():
        sb.table('lessons').insert({
            'course_id': course_id,
            'title': form.title.data,
            'file_path': form.youtube_id.data,
            'lesson_type': 'youtube'
        }).execute()
        flash('YouTube lesson added!', 'success')
        return redirect(url_for('main.course_detail', course_id=course_id))
    return render_template('admin/create_lesson_youtube.html', title='Add YouTube Lesson', form=form, course=course_res.data)


@main.route("/admin/lesson/<int:lesson_id>/update", methods=['GET', 'POST'])
@admin_required
def update_lesson(lesson_id):
    sb = get_supabase()
    lesson_res = sb.table('lessons').select('*').eq('id', lesson_id).single().execute()
    if not lesson_res.data:
        abort(404)
    
    lesson = lesson_res.data
    form = TextLessonForm() if lesson['lesson_type'] == 'text' else YouTubeLessonForm() # Fallback for title
    
    if form.validate_on_submit():
        update_data = {'title': form.title.data}
        if lesson['lesson_type'] == 'text':
            update_data['content'] = form.content.data
        elif lesson['lesson_type'] == 'youtube':
            update_data['file_path'] = form.youtube_id.data
        
        sb.table('lessons').update(update_data).eq('id', lesson_id).execute()
        flash('Lesson updated!', 'success')
        return redirect(url_for('main.course_detail', course_id=lesson['course_id']))
    
    if request.method == 'GET':
        form.title.data = lesson['title']
        if lesson['lesson_type'] == 'text':
            form.content.data = lesson['content']
        elif lesson['lesson_type'] == 'youtube':
            form.youtube_id.data = lesson['file_path']
            
    return render_template('admin/update_lesson_file.html', title='Update Lesson', form=form, lesson=lesson, legend='Update Lesson')


@main.route("/admin/lesson/<int:lesson_id>/delete", methods=['POST'])
@admin_required
def delete_lesson(lesson_id):
    sb = get_supabase()
    lesson_res = sb.table('lessons').select('id, course_id, file_path, lesson_type').eq('id', lesson_id).single().execute()
    if not lesson_res.data:
        abort(404)
    
    course_id = lesson_res.data['course_id']
    try:
        # Optionally delete physical file
        if lesson_res.data['lesson_type'] in ['file', 'video'] and lesson_res.data['file_path']:
             subfolder = 'lessons/docs' if lesson_res.data['lesson_type'] == 'file' else 'lessons/videos'
             file_path = os.path.join(current_app.root_path, 'uploads', subfolder, lesson_res.data['file_path'])
             if os.path.exists(file_path):
                 os.remove(file_path)
        
        sb.table('lessons').delete().eq('id', lesson_id).execute()
        flash('Lesson deleted!', 'success')
    except Exception as e:
        logger.error(f"Error deleting lesson: {e}")
        flash('Error deleting lesson.', 'danger')
        
    return redirect(url_for('main.course_detail', course_id=course_id))


@main.route("/admin/lesson/<int:lesson_id>/view")
@admin_required
def view_lesson(lesson_id):
    sb = get_supabase()
    lesson_res = sb.table('lessons').select('*').eq('id', lesson_id).single().execute()
    if not lesson_res.data:
        abort(404)
    
    lesson = Lesson.from_dict(lesson_res.data)
    if lesson.lesson_type != 'text':
        # Files/Videos are better served via uploaded_file or direct link
        return redirect(url_for('main.course_detail', course_id=lesson.course_id))
        
    # We'll use a simple view for text lessons
    return render_template('admin/create_lesson_text.html', title=lesson.title, form=None, lesson=lesson, view_only=True, course={'id': lesson.course_id, 'title': 'Preview'})



@main.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    form = OnboardingForm()
    if form.validate_on_submit():
        ambition = form.ambition.data
        hours = form.study_hours.data
        remind_time = form.reminder_time.data

        sb = get_supabase()
        # Update user preferences
        sb.table('users').update({
            'daily_study_hours': hours,
            'study_reminder_time': str(remind_time),
        }).eq('id', current_user.id).execute()

        try:
            ai_service = AIService()
            roadmap_data = ai_service.generate_roadmap(ambition, hours)

            banner_image_url = ai_service.generate_banner(ambition)

            if not roadmap_data or "steps" not in roadmap_data:
                flash('AI fallback used for roadmap.', 'warning')
                roadmap_data = ai_service._mock_roadmap(ambition)

            goal_title = roadmap_data.get('goal', ambition)

            # Insert roadmap
            roadmap_result = sb.table('generated_roadmaps').insert({
                'goal': goal_title,
                'content': json.dumps(roadmap_data),
                'image_url': banner_image_url,
                'user_id': current_user.id,
            }).execute()

            roadmap_id = roadmap_result.data[0]['id']

            # Insert steps
            for step in roadmap_data.get('steps', []):
                sb.table('roadmap_steps').insert({
                    'step_number': step.get('step_number'),
                    'title': step.get('title'),
                    'description': step.get('description'),
                    'youtube_queries': json.dumps(step.get('youtube_queries', [])),
                    'status': 'not_started',
                    'roadmap_id': roadmap_id,
                }).execute()

            flash('Your personalized ADC roadmap has been generated!', 'success')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            current_app.logger.error(f"Onboarding Error: {e}")
            flash(f'An error occurred: {e}', 'danger')

    return render_template('student/onboarding.html', title='Create Your Path', form=form)


@main.route('/onboarding/success')
@login_required
def onboarding_success():
    return render_template('student/onboarding_success.html', title='Roadmap Generated!')


# ============================================================
# GOOGLE CALENDAR SYNC
# ============================================================

@main.route('/google-calendar/auth')
@login_required
def google_calendar_auth():
    """Start Google Calendar OAuth flow."""
    service = GoogleCalendarService()
    auth_url = service.get_auth_url()
    return redirect(auth_url)


@main.route('/google-calendar/callback')
@login_required
def google_calendar_callback():
    """Handle Google Calendar OAuth callback."""
    code = request.args.get('code')
    if not code:
        flash('Authorization failed.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        service = GoogleCalendarService()
        credentials = service.fetch_token(code)
        # Store credentials in session (simple approach)
        session['google_calendar_credentials'] = credentials.to_json()
        flash('Google Calendar connected!', 'success')
    except Exception as e:
        flash(f'Error connecting to Google Calendar: {e}', 'danger')
        
    return redirect(url_for('main.dashboard'))


@main.route('/roadmap/step/<int:step_id>/sync-calendar', methods=['POST'])
@login_required
def sync_to_google_calendar(step_id):
    """Sync a specific step to Google Calendar."""
    if 'google_calendar_credentials' not in session:
        return redirect(url_for('main.google_calendar_auth'))
    
    # Get step details from Supabase
    sb = get_supabase()
    step_res = sb.table('roadmap_steps').select('*').eq('id', step_id).single().execute()
    if not step_res.data:
        abort(404)
    
    step = step_res.data
    
    import google.oauth2.credentials
    creds_json = session['google_calendar_credentials']
    credentials = google.oauth2.credentials.Credentials.from_authorized_user_json(creds_json)
    
    try:
        service = GoogleCalendarService()
        # Schedule for tomorrow at 10 AM by default for demo
        start_time = (datetime.utcnow() + timedelta(days=1)).replace(hour=10, minute=0, second=0).isoformat() + 'Z'
        
        event_link = service.create_event(
            credentials,
            title=step['title'],
            description=step['description'],
            start_time=start_time
        )
        flash(f'Event created! <a href="{event_link}" target="_blank">View in Calendar</a>', 'success')
    except Exception as e:
        flash(f'Failed to create event: {e}', 'danger')
        
    return redirect(url_for('main.dashboard'))


# ============================================================
# STUDENT CONTENT GENERATION ROUTES
# ============================================================

@main.route('/roadmap/step/<int:step_id>/generate_lecture', methods=['POST'])
@login_required
def generate_step_lecture(step_id):
    """Student triggers AI lecture + audio generation for a roadmap step."""
    sb = get_supabase()

    # Get the step
    step_result = sb.table('roadmap_steps').select('*').eq('id', step_id).single().execute()
    if not step_result.data:
        abort(404)
    step_data = step_result.data

    # Verify ownership
    roadmap_result = sb.table('generated_roadmaps').select('user_id').eq('id', step_data['roadmap_id']).single().execute()
    if not roadmap_result.data or roadmap_result.data['user_id'] != current_user.id:
        abort(403)

    ai_service = AIService()

    # Generate lecture text
    lecture_text = ai_service.generate_lecture_content(step_data['title'], step_data['description'])

    # Generate audio
    audio_dir = os.path.join(current_app.root_path, 'uploads', 'audio')
    os.makedirs(audio_dir, exist_ok=True)
    audio_filename = ai_service.generate_audio_explanation(lecture_text, audio_dir)

    # Update step in Supabase
    update_data = {'lecture_content': lecture_text}
    if audio_filename:
        update_data['audio_url'] = audio_filename
    
    sb.table('roadmap_steps').update(update_data).eq('id', step_id).execute()

    flash('Lecture and audio generated successfully!', 'success')
    return redirect(url_for('main.view_step_lesson', step_id=step_id))


@main.route('/roadmap/step/<int:step_id>/lesson')
@login_required
def view_step_lesson(step_id):
    """View the detailed AI-generated lesson for a roadmap step."""
    sb = get_supabase()

    # Get the step
    step_result = sb.table('roadmap_steps').select('*').eq('id', step_id).single().execute()
    if not step_result.data:
        abort(404)
    step_data = step_result.data

    # Verify ownership
    roadmap_result = sb.table('generated_roadmaps').select('user_id').eq('id', step_data['roadmap_id']).single().execute()
    if not roadmap_result.data or roadmap_result.data['user_id'] != current_user.id:
        abort(403)

    if not step_data['lecture_content']:
        flash('Please generate the lesson first.', 'warning')
        return redirect(url_for('main.dashboard'))

    # Conver dict to a helper object or just use as is in template
    # Since Template uses step.title, we'll keep it as dict or use a simple class
    from .models import RoadmapStep
    step = RoadmapStep.from_dict(step_data)

    return render_template('student/detailed_lesson.html', title=step.title, step=step)


@main.route('/roadmap/<int:roadmap_id>/download_schedule')
@login_required
def download_schedule(roadmap_id):
    sb = get_supabase()

    # Get roadmap
    roadmap_result = sb.table('generated_roadmaps').select('*').eq('id', roadmap_id).single().execute()
    if not roadmap_result.data or roadmap_result.data['user_id'] != current_user.id:
        abort(403)

    # Get steps
    steps_result = sb.table('roadmap_steps').select('*').eq('roadmap_id', roadmap_id).order('step_number').execute()
    steps = [RoadmapStep.from_dict(s) for s in steps_result.data] if steps_result.data else []
    roadmap = GeneratedRoadmap.from_dict(roadmap_result.data, steps=steps)

    ics_content = CalendarService.create_schedule(roadmap)

    return Response(
        ics_content,
        mimetype="text/calendar",
        headers={"Content-disposition": f"attachment; filename=study_schedule_{roadmap.id}.ics"}
    )


# ============================================================
# AI TUTOR
# ============================================================

@main.route('/ai-tutor')
@login_required
def ai_tutor():
    sb = get_supabase()
    session_id = request.args.get('session', '1')
    
    # 1. Fetch unique sessions for this user (with titles!)
    sessions_res = sb.table('chat_sessions').select('*').eq('user_id', current_user.id).order('updated_at', desc=True).execute()
    
    unique_sessions = []
    if sessions_res.data:
        unique_sessions = sessions_res.data
    else:
        # Fallback or empty state handled by template
        pass

    # If new session param is requested but doesn't exist in DB yet (e.g. brand new chat not started), handle it gracefully
    # The template will show it as active but it won't be in the list until first message
    
    if not unique_sessions and session_id == '1':
        # Create a default list item for UI if empty
        unique_sessions = [{'id': '1', 'title': 'New Chat'}]

    # 2. Fetch messages for the current session (unchanged)

    # 2. Fetch messages for the current session
    messages_res = sb.table('chat_messages').select('*, users(*)').eq('session_id', session_id).eq('user_id', current_user.id).order('created_at').execute()
    
    chat_messages = []
    if messages_res.data:
        for m in messages_res.data:
            sender_id = m.get('sender_id')
            if sender_id is None:
                sender_name = 'Autodidatic_AI'
            else:
                sender_name = current_user.username
            chat_messages.append({
                'sender': sender_name,
                'content': m['content'],
                'timestamp': m['created_at'] # We'll format this in Jinja or JS
            })

    return render_template('student/ai_tutor.html', 
                           title='AI Tutor', 
                           sessions=unique_sessions, 
                           current_session=session_id,
                           messages=chat_messages)


@main.route('/ai-tutor/rename', methods=['POST'])
@login_required
def rename_session():
    data = request.get_json()
    session_id = data.get('session_id')
    new_title = data.get('title')
    
    if not session_id or not new_title:
        return jsonify({'error': 'Missing data'}), 400
        
    sb = get_supabase()
    # Verify ownership
    res = sb.table('chat_sessions').select('user_id').eq('id', session_id).single().execute()
    if not res.data or res.data['user_id'] != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    sb.table('chat_sessions').update({'title': new_title}).eq('id', session_id).execute()
    return jsonify({'success': True})


@main.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    sb = get_supabase()
    updates = {}
    
    # Handle Avatar Upload
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename:
            filename = secrets.token_hex(8) + "_" + file.filename
            file_path = os.path.join(current_app.root_path, 'uploads/avatars', filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            updates['avatar_url'] = f'/uploads/avatars/{filename}'
            
    # Handle Wallpaper Upload
    if 'wallpaper' in request.files:
        file = request.files['wallpaper']
        if file and file.filename:
            filename = secrets.token_hex(8) + "_" + file.filename
            file_path = os.path.join(current_app.root_path, 'uploads/wallpapers', filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            updates['wallpaper_url'] = f'/uploads/wallpapers/{filename}'
            
    if updates:
        try:
            sb.table('users').update(updates).eq('id', current_user.id).execute()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            logger.error(f"Error updating profile: {e}")
            return jsonify({'error': 'Database update failed'}), 500
            
    return jsonify({'success': True, 'updates': updates})


# ============================================================
# FILE SERVING
# ============================================================

@main.route('/uploads/<path:subfolder>/<path:filename>')
@login_required
def uploaded_file(subfolder, filename):
    return send_from_directory(os.path.join(current_app.root_path, f'uploads/{subfolder}'), filename)
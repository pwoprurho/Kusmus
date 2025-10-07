import os
import secrets
import re
import docker
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import google.generativeai as genai
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory, abort, session, jsonify
from flask_login import login_user, current_user, logout_user, login_required
from kusmusapp import db
from kusmusapp.models import (User, Course, Lesson, GeneratedRoadmap, RoadmapStep, 
                            Module, Assignment, AssignmentSubmission, Post, Comment, Vote, ChatSession, admin_required)
from kusmusapp.forms import (RegistrationForm, LoginForm, CourseForm, 
                           TextLessonForm, FileLessonForm, VideoLessonForm, YouTubeLessonForm, OnboardingForm,
                           ModuleForm, AssignmentForm, PostForm, CommentForm, GradingForm)
from sqlalchemy import or_

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

def run_python_code(code_string):
    """Runs a string of Python code in a secure, isolated Docker container."""
    try:
        client = docker.from_env()
        client.ping()
    except Exception as e:
        print(f"!!! DOCKER CONNECTION FAILED: {e}")
        return {'output': '', 'error': f'Could not connect to Docker service. Error: {e}'}
    try:
        container = client.containers.run(
            'python:3.10-slim', command=['python', '-c', code_string],
            mem_limit='128m', cpu_shares=128, network_disabled=True, detach=True
        )
        result = container.wait(timeout=10)
        stdout = container.logs(stdout=True, stderr=False).decode('utf-8')
        stderr = container.logs(stdout=False, stderr=True).decode('utf-8')
        container.remove()
        if result['StatusCode'] == 0:
            return {'output': stdout, 'error': ''}
        else:
            return {'output': stdout, 'error': stderr}
    except Exception as e:
        if 'container' in locals() and container: container.remove(force=True)
        return {'output': '', 'error': f'An unexpected error occurred: {e}'}

def grade_python_code(user_code, test_cases_json):
    """Runs user code against a set of test cases in Docker."""
    try:
        client = docker.from_env()
        client.ping()
    except Exception as e:
        print(f"!!! DOCKER CONNECTION FAILED: {e}")
        return [{'status': 'error', 'details': f'Could not connect to Docker service. Error: {e}'}]
    
    results = []
    try:
        test_cases = json.loads(test_cases_json)
    except (json.JSONDecodeError, TypeError):
        return [{'status': 'error', 'details': 'Failed to parse test cases for this assignment.'}]
        
    for i, case in enumerate(test_cases):
        case_input = case.get('input', [])
        expected_output = case.get('expected_output')
        input_str = ", ".join(map(repr, case_input))
        
        full_script = f"""
import json
import sys
{user_code}
try:
    func_name = [name for name, obj in locals().items() if callable(obj) and obj.__module__ == '__main__'][0]
    user_func = locals()[func_name]
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    actual_output = user_func({input_str})
    sys.stdout = original_stdout
    expected_output = {repr(expected_output)}
    if actual_output == expected_output:
        print(json.dumps({{"status": "pass", "input": {repr(case_input)}, "output": repr(actual_output), "expected": repr(expected_output)}}))
    else:
        print(json.dumps({{"status": "fail", "input": {repr(case_input)}, "output": repr(actual_output), "expected": repr(expected_output)}}))
except Exception as e:
    if 'original_stdout' in locals():
        sys.stdout = original_stdout
    print(json.dumps({{"status": "error", "input": {repr(case_input)}, "details": str(e)}}))
"""
        try:
            container = client.containers.run(
                'python:3.10-slim', command=['python', '-c', full_script],
                mem_limit='128m', cpu_shares=128, network_disabled=True, detach=True
            )
            result = container.wait(timeout=10)
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8').strip()
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8').strip()
            container.remove()
            if not stdout:
                results.append({'status': 'error', 'input': case_input, 'details': stderr})
            else:
                results.append(json.loads(stdout))
        except Exception as e:
            if 'container' in locals() and container: container.remove(force=True)
            results.append({'status': 'error', 'input': case_input, 'details': f'Execution timed out or crashed: {e}'})
            
    return results

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

# --- COMMUNITY HUB ROUTES ---
@main.route("/community")
@login_required
def community():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('community/community.html', title='Community', posts=posts)

@main.route("/post/new", methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created!', 'success')
        return redirect(url_for('main.community'))
    return render_template('community/create_post.html', title='New Post', form=form, legend='New Post')

@main.route("/post/<int:post_id>", methods=['GET', 'POST'])
@login_required
def post(post_id):
    post = Post.query.get_or_404(post_id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(content=form.content.data, post=post, author=current_user)
        db.session.add(comment)
        db.session.commit()
        flash('Your comment has been published.', 'success')
        return redirect(url_for('main.post', post_id=post.id))
    comments = Comment.query.filter_by(post_id=post.id).order_by(Comment.date_posted.asc()).all()
    return render_template('community/post_detail.html', title=post.title, post=post, form=form, comments=comments)

@main.route("/post/<int:post_id>/vote", methods=['POST'])
@login_required
def vote(post_id):
    post = Post.query.get_or_404(post_id)
    vote_type = request.json.get('vote_type')
    if vote_type not in ['coin', 'slander']:
        return jsonify({'error': 'Invalid vote type'}), 400
    vote_value = 1 if vote_type == 'coin' else -1
    existing_vote = Vote.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    if existing_vote:
        if existing_vote.value == vote_value:
            db.session.delete(existing_vote)
        else:
            existing_vote.value = vote_value
    else:
        new_vote = Vote(user_id=current_user.id, post_id=post.id, value=vote_value)
        db.session.add(new_vote)
    db.session.commit()
    user_vote = Vote.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    return jsonify({'score': post.score, 'user_vote': user_vote.value if user_vote else 0})

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
            text_model = genai.GenerativeModel('models/gemini-2.5-flash')
            text_prompt = f"""Generate a 7-step learning roadmap for a user who wants to '{ambition}'. The user can study for {hours} hours a day. Format the output strictly as a numbered list. Each item must start with 'Step X:'. Each step must have a title and a one-sentence description. Example: Step 1: Title of Step 1. A brief description of this step."""
            text_response = text_model.generate_content(text_prompt)
            roadmap_text = text_response.text
            banner_model = genai.GenerativeModel('models/gemini-2.5-flash-image')
            banner_prompt = f"Generate a visually appealing, abstract, motivational banner image for a '{ambition}' tech career roadmap. Style: digital art, futuristic, clean, vibrant colors."
            banner_response = banner_model.generate_content(banner_prompt)
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

# --- STUDENT-FACING CONTENT ROUTES ---
@main.route('/courses')
@login_required
def course_catalog():
    courses = Course.query.order_by(Course.date_posted.desc()).all()
    return render_template('student/course_catalog.html', title='Courses', courses=courses)

@main.route('/learn/course/<int:course_id>')
@login_required
def student_course_view(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template('student/student_course_view.html', title=course.title, course=course)

@main.route('/notebook')
@login_required
def notebook():
    return render_template('student/notebook.html', title='Jupyter Notebook')

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

@main.route("/course/<int:course_id>/add_module", methods=['GET', 'POST'])
@login_required
@admin_required
def add_module(course_id):
    course = Course.query.get_or_404(course_id)
    form = ModuleForm()
    if form.validate_on_submit():
        module = Module(title=form.title.data, course=course)
        db.session.add(module)
        db.session.commit()
        flash('New module has been created!', 'success')
        return redirect(url_for('main.course_detail', course_id=course.id))
    return render_template('admin/create_module.html', title='New Module', form=form, course=course)

@main.route("/module/<int:module_id>/add_assignment", methods=['GET', 'POST'])
@login_required
@admin_required
def add_assignment(module_id):
    module = Module.query.get_or_404(module_id)
    form = AssignmentForm()
    if form.validate_on_submit():
        assignment = Assignment(title=form.title.data, instructions=form.instructions.data, due_date=form.due_date.data, module=module)
        if 'solution_code' in request.form and request.form['solution_code']:
            assignment.solution_code = request.form['solution_code']
        if 'test_cases' in request.form and request.form['test_cases']:
            assignment.test_cases = request.form['test_cases']
        db.session.add(assignment)
        db.session.commit()
        flash('New assignment has been created!', 'success')
        return redirect(url_for('main.course_detail', course_id=module.course_id))
    return render_template('admin/create_assignment.html', title='New Assignment', form=form, module=module)

@main.route('/generate-challenge', methods=['POST'])
@login_required
@admin_required
def generate_challenge():
    topic = request.json.get('topic')
    if not topic:
        return jsonify({'error': 'No topic provided'}), 400
    try:
        API_KEY = os.getenv('GEMINI_API_KEY')
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        prompt = f"""
        You are a computer science professor creating a Python coding challenge. The topic is '{topic}'.
        Generate a coding challenge with the following components in a single, valid JSON object:
        1. "title": A concise title for the challenge.
        2. "instructions": A clear problem description for a beginner, formatted in markdown.
        3. "solution_code": A correct, standard Python solution. This solution must be a single function.
        4. "test_cases": An array of 4 simple test cases. Each test case must be an object with an "input" array (the arguments for the solution function) and an "expected_output".
        
        Example for topic 'add two numbers':
        {{
            "title": "Sum of Two Integers",
            "instructions": "Write a Python function `add(a, b)` that takes two integers as input and returns their sum.",
            "solution_code": "def add(a, b):\\n    return a + b",
            "test_cases": [
                {{"input": [2, 3], "expected_output": 5}},
                {{"input": [-1, 1], "expected_output": 0}},
                {{"input": [10, 20], "expected_output": 30}},
                {{"input": [0, 0], "expected_output": 0}}
            ]
        }}
        """
        generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
        response = model.generate_content(prompt, generation_config=generation_config)
        cleaned_text = re.sub(r'```json\n|\n```', '', response.text).strip()
        data = json.loads(cleaned_text)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        subfolder = 'lessons/docs' if lesson.lesson_type == 'file' else 'videos'
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

@main.route('/assignment/<int:assignment_id>/submissions')
@login_required
@admin_required
def view_submissions(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    return render_template('admin/view_submissions.html', title='Submissions', assignment=assignment)

@main.route('/submission/<int:submission_id>/grade', methods=['GET', 'POST'])
@login_required
@admin_required
def grade_submission(submission_id):
    submission = AssignmentSubmission.query.get_or_404(submission_id)
    form = GradingForm()
    if form.validate_on_submit():
        submission.grade = form.grade.data
        submission.feedback = form.feedback.data
        db.session.commit()
        flash('The grade has been submitted.', 'success')
        return redirect(url_for('main.view_submissions', assignment_id=submission.assignment_id))
    elif request.method == 'GET':
        form.grade.data = submission.grade
        form.feedback.data = submission.feedback
    return render_template('admin/grade_submission.html', title='Grade Submission', form=form, submission=submission)

@main.route('/run_code_simple', methods=['POST'])
@login_required
def run_code_simple():
    code = request.json.get('code', '')
    result = run_python_code(code)
    return jsonify(result)

@main.route('/run_code', methods=['POST'])
@login_required
def run_code():
    data = request.get_json()
    user_code = data.get('code', '')
    assignment_id = data.get('assignment_id')
    assignment = Assignment.query.get_or_404(assignment_id)
    if not assignment.test_cases:
        return jsonify({'error': 'No test cases found for this assignment.'}), 400
    results = grade_python_code(user_code, assignment.test_cases)
    summary = {'total': len(results), 'passed': sum(1 for r in results if r.get('status') == 'pass')}
    return jsonify({'summary': summary, 'results': results})

@main.route('/assignment/<int:assignment_id>/solve')
@login_required
def solve_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    starter_code = f'# Solve the challenge for "{assignment.title}" here\n\n'
    return render_template('student/solve_assignment.html', assignment=assignment, starter_code=starter_code)
    
@main.route('/assignment/<int:assignment_id>/submit', methods=['POST'])
@login_required
def submit_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    submitted_code = request.form.get('code')
    existing_submission = AssignmentSubmission.query.filter_by(student=current_user, assignment=assignment).first()
    if existing_submission:
        existing_submission.content = submitted_code
        existing_submission.date_submitted = datetime.utcnow()
        flash('Your submission has been updated!', 'success')
    else:
        submission = AssignmentSubmission(content=submitted_code, student=current_user, assignment=assignment)
        db.session.add(submission)
        flash('Your assignment has been submitted successfully!', 'success')
    db.session.commit()
    return redirect(url_for('main.solve_assignment', assignment_id=assignment.id))

@main.route('/uploads/<path:subfolder>/<path:filename>')
@login_required
def uploaded_file(subfolder, filename):
    return send_from_directory(os.path.join(current_app.root_path, f'uploads/{subfolder}'), filename)

# --- MESSAGING ROUTES ---


# --- MESSAGING ROUTES ---
@main.route('/messages')
@login_required
def messages():
    """Main messenger page. Redirects to the most recent chat or find users page."""
    # This now works because current_user.chat_sessions is a query object
    latest_chat = current_user.chat_sessions.order_by(ChatSession.id.desc()).first()
    if latest_chat:
        return redirect(url_for('main.chat_view', session_id=latest_chat.id))
    return redirect(url_for('main.find_users'))

@main.route('/messages/find')
@login_required
def find_users():
    """Page to display all users to start a new chat."""
    all_users = User.query.filter(User.id != current_user.id).all()
    return render_template('student/contacts.html', title='Start a New Chat', users=all_users)

@main.route('/messages/view/<int:session_id>')
@login_required
def chat_view(session_id):
    """Displays a specific chat session."""
    current_chat = ChatSession.query.get_or_404(session_id)
    if current_user not in current_chat.participants and not current_chat.is_ai_chat:
        abort(403)

    # This now works because current_user.chat_sessions is a query object
    all_user_chats = current_user.chat_sessions.order_by(ChatSession.id.desc()).all()
    
    return render_template('student/chat.html', 
                           title='Messages', 
                           current_chat=current_chat, 
                           all_chats=all_user_chats)

@main.route('/messages/start/<int:recipient_id>', methods=['POST'])
@login_required
def start_chat(recipient_id):
    """Creates a new chat session if one doesn't already exist, then redirects to it."""
    recipient = User.query.get_or_404(recipient_id)
    chat = ChatSession.query.filter(ChatSession.is_ai_chat == False)\
        .filter(ChatSession.participants.contains(current_user))\
        .filter(ChatSession.participants.contains(recipient)).first()
    if not chat:
        chat = ChatSession(is_ai_chat=False)
        chat.participants.append(current_user)
        chat.participants.append(recipient)
        db.session.add(chat)
        db.session.commit()
        flash(f'Chat with {recipient.username} started!', 'success')
    return redirect(url_for('main.chat_view', session_id=chat.id))
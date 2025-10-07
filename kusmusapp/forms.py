from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, TimeField, FloatField, DateField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, URL, NumberRange
from kusmusapp.models import User

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user: raise ValidationError('That username is already taken.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user: raise ValidationError('That email is already in use.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class OnboardingForm(FlaskForm):
    ambition = StringField('What is your learning ambition or career goal?', 
                           validators=[DataRequired()], 
                           render_kw={"placeholder": "e.g., Become a frontend developer specializing in e-commerce"})
    study_hours = FloatField('How many hours per day can you commit to studying?', 
                             validators=[DataRequired(), NumberRange(min=0.5, max=12)])
    reminder_time = TimeField('What time of day should we remind you to study?', 
                              format='%H:%M', 
                              validators=[DataRequired()])
    submit = SubmitField('Generate My Roadmap with Kustor_AI')

class CourseForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=5, max=100)])
    description = TextAreaField('Description', validators=[DataRequired()])
    submit = SubmitField('Create Course')

class TextLessonForm(FlaskForm):
    title = StringField('Lesson Title', validators=[DataRequired()])
    content = TextAreaField('Lesson Content', validators=[DataRequired()])
    submit = SubmitField('Create Text Lesson')

class FileLessonForm(FlaskForm):
    title = StringField('Lesson Title', validators=[DataRequired()])
    document = FileField('Lesson Document (PDF, DOC, DOCX)', validators=[DataRequired(), FileAllowed(['pdf', 'doc', 'docx'])])
    submit = SubmitField('Upload File Lesson')

class VideoLessonForm(FlaskForm):
    title = StringField('Lesson Title', validators=[DataRequired()])
    video = FileField('Lesson Video (MP4, MOV)', validators=[DataRequired(), FileAllowed(['mp4', 'mov', 'avi'])])
    submit = SubmitField('Upload Video Lesson')

class YouTubeLessonForm(FlaskForm):
    title = StringField('Lesson Title', validators=[DataRequired()])
    youtube_url = StringField('YouTube URL', validators=[DataRequired(), URL()])
    submit = SubmitField('Add YouTube Lesson')

class ModuleForm(FlaskForm):
    title = StringField('Module Title', validators=[DataRequired()])
    submit = SubmitField('Create Module')

class AssignmentForm(FlaskForm):
    title = StringField('Assignment Title', validators=[DataRequired()])
    instructions = TextAreaField('Instructions', validators=[DataRequired()])
    due_date = DateField('Due Date (Optional, Format: YYYY-MM-DD)', format='%Y-%m-%d', validators=[])
    submit = SubmitField('Create Assignment')

class PostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    content = TextAreaField('Content', validators=[DataRequired()])
    submit = SubmitField('Create Post')

class CommentForm(FlaskForm):
    content = TextAreaField('Comment', validators=[DataRequired()])
    submit = SubmitField('Submit')

class GradingForm(FlaskForm):
    grade = StringField('Grade (e.g., A+, 95%)', validators=[DataRequired()])
    feedback = TextAreaField('Feedback')
    submit = SubmitField('Submit Grade')
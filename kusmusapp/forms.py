from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, TimeField, FloatField, SelectField, IntegerField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, URL, NumberRange
from kusmusapp.services.supabase_client import get_supabase

# User Auth Forms
class RegistrationForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone_number = StringField('Phone Number', validators=[DataRequired(), Length(min=7, max=15)])
    
    # Location data
    state = SelectField('State', choices=[], validators=[DataRequired()])
    lga = SelectField('Local Government Area', choices=[], validators=[DataRequired()])
    
    # Personal Info
    gender = SelectField('Gender', choices=[('', 'Select Gender'), ('male', 'Male'), ('female', 'Female')], validators=[DataRequired()])
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=10, max=100)])

    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        sb = get_supabase()
        result = sb.table('users').select('id').eq('username', username.data).execute()
        if result.data:
            raise ValidationError('That username is already taken.')

    def validate_email(self, email):
        sb = get_supabase()
        result = sb.table('users').select('id').eq('email', email.data).execute()
        if result.data:
            raise ValidationError('That email is already in use.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

# Student Forms
class OnboardingForm(FlaskForm):
    ambition = StringField('What is your learning ambition or career goal?', 
                           validators=[DataRequired()], 
                           render_kw={"placeholder": "e.g., Become a frontend developer specializing in e-commerce"})
    study_hours = FloatField('How many hours per day can you commit to studying?', 
                             validators=[DataRequired(), NumberRange(min=0.5, max=12)])
    reminder_time = TimeField('What time of day should we remind you to study?', 
                              format='%H:%M', 
                              validators=[DataRequired()])
    submit = SubmitField('Generate My Roadmap with Autodidatic_AI')


# Course Management Forms
class CourseForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    submit = SubmitField('Save Course')


class TextLessonForm(FlaskForm):
    title = StringField('Lesson Title', validators=[DataRequired()])
    content = TextAreaField('Content', validators=[DataRequired()])
    submit = SubmitField('Save Lesson')


class FileLessonForm(FlaskForm):
    title = StringField('Lesson Title', validators=[DataRequired()])
    file = FileField('Lesson File (PDF, DOCX)', 
                    validators=[DataRequired(), FileAllowed(['pdf', 'docx', 'doc'])])
    submit = SubmitField('Upload File Lesson')


class VideoLessonForm(FlaskForm):
    title = StringField('Lesson Title', validators=[DataRequired()])
    video = FileField('Lesson Video (MP4)', 
                     validators=[DataRequired(), FileAllowed(['mp4', 'mov', 'avi'])])
    submit = SubmitField('Upload Video Lesson')


class YouTubeLessonForm(FlaskForm):
    title = StringField('Lesson Title', validators=[DataRequired()])
    youtube_id = StringField('YouTube Video ID (e.g., dQw4w9WgXcQ)', validators=[DataRequired()])
    submit = SubmitField('Add YouTube Lesson')

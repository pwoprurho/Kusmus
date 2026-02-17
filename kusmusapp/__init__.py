import os
from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO

# Load environment variables from .env file
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(os.path.dirname(basedir), '.env'))

# Create extension instances without an app
bcrypt = Bcrypt()
login_manager = LoginManager()
socketio = SocketIO()

login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'

def create_app():
    # --- APP CONFIGURATION ---
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-very-secret-and-secure-key-for-production')
    app.config['SUPABASE_URL'] = os.getenv('SUPABASE_URL')
    app.config['SUPABASE_KEY'] = os.getenv('SUPABASE_KEY')

    # --- INITIALIZE EXTENSIONS WITH THE APP ---
    bcrypt.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)

    # --- REGISTER BLUEPRINTS ---
    from kusmusapp.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Import models to register the user_loader with login_manager
    from . import models

    # Import socket events after app is created to avoid circular imports
    from . import sockets

    return app
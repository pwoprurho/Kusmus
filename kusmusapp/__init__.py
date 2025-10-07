import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO

# Load environment variables from .env file
load_dotenv()

# --- CREATE EXTENSIONS ---
db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
login_manager = LoginManager()

# This wildcard is the most robust setting for Codespaces
socketio = SocketIO(cors_allowed_origins="*") # <-- THIS IS THE FIX

login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'

def create_app():
    """Application Factory Function"""
    app = Flask(__name__)
    
    # --- APP CONFIGURATION ---
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__name__)), 'kusmus.db')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-default-secret-key')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --- INITIALIZE EXTENSIONS WITH THE APP ---
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)

    # --- REGISTER BLUEPRINTS & ROUTES ---
    from kusmusapp.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Import socket events to register them
    from . import sockets

    return app
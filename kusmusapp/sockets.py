import os
import google.generativeai as genai
from datetime import datetime
from flask_login import current_user
from flask_socketio import emit, join_room
from . import socketio
from .models import ChatMessage, db

@socketio.on('join')
def on_join(data):
    """User joins a chat room."""
    username = current_user.username
    room = data['room']
    join_room(room)
    print(f'{username} has entered the room: {room}')

@socketio.on('send_message')
def handle_send_message(data):
    """Receive a message, save it, check for AI commands, and broadcast."""
    room = data['room'] 
    message_content = data['message']
    
    # --- Regular chat message ---
    if not message_content.lower().strip().startswith('generate'):
        msg = ChatMessage(content=message_content, sender_id=current_user.id, session_id=room)
        db.session.add(msg)
        db.session.commit()
        emit('receive_message', {
            'sender': current_user.username, 'content': message_content,
            'timestamp': msg.timestamp.strftime('%H:%M')
        }, room=room)
        return

    # --- AI command processing ---
    print(f"Received AI command: {message_content}")
    try:
        API_KEY = os.getenv('GEMINI_API_KEY')
        if not API_KEY:
            raise Exception("GEMINI_API_KEY is not configured.")
        genai.configure(api_key=API_KEY)
        
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        prompt = f"You are Kustor_AI, an expert instructor. A student's request is: '{message_content}'. Generate a detailed, beginner-friendly lesson. Use markdown for formatting."
        
        response_stream = model.generate_content(prompt, stream=True)
        
        full_ai_response = ""
        emit('stream_start', {'sender': 'Kustor_AI'}, room=room)

        for chunk in response_stream:
            if chunk.text:
                emit('stream_chunk', {'chunk': chunk.text}, room=room)
                full_ai_response += chunk.text

        ai_msg = ChatMessage(content=full_ai_response, sender_id=1, session_id=room)
        db.session.add(ai_msg)
        db.session.commit()

        emit('stream_end', {'timestamp': ai_msg.timestamp.strftime('%H:%M')}, room=room)

    except Exception as e:
        print(f"!!! AI GENERATION ERROR: {e}")
        error_content = f"Sorry, I ran into an error. Details: {str(e)}"
        emit('receive_message', {
            'sender': 'Kustor_AI', 'content': error_content,
            'timestamp': datetime.utcnow().strftime('%H:%M')
        }, room=room)
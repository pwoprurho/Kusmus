import os
import json
import google.generativeai as genai
from datetime import datetime
from flask_login import current_user
from flask_socketio import emit, join_room
from . import socketio
from .services.supabase_client import get_supabase

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
    sb = get_supabase()
    user_id_captured = current_user.id
    username_captured = current_user.username
    
    # --- Ensure Session Exists ---
    # We do this for both regular and AI messages to ensure the session is tracked
    try:
        # Check if session exists (or just try insert on conflict do nothing if Supabase/Postgres supports it easier)
        # Supabase-py doesn't support 'on_conflict' easily in insert/upsert without specific config, 
        # so we'll do a quick check-and-insert.
        res = sb.table('chat_sessions').select('id').eq('id', room).execute()
        if not res.data:
            sb.table('chat_sessions').insert({
                'id': room,
                'user_id': current_user.id,
                'title': 'New Chat',
                'created_at': datetime.utcnow().isoformat()
            }).execute()
        else:
             # Optionally update updated_at
             sb.table('chat_sessions').update({
                 'updated_at': datetime.utcnow().isoformat()
             }).eq('id', room).execute()
             
    except Exception as session_err:
        print(f"Session creation error: {session_err}")
        # Continue anyway, let chat_messages insert fail if FK enforced (it's not yet enforced in DB except by my migration, but old table might strictly enforce it if I added FK)
        # Actually my migration added FK? "user_id BIGINT REFERENCES public.users(id)". It did NOT add FK to session_id in chat_messages (kept it as TEXT).
        pass

    # --- 1. Save and Broadcast USER Message ---
    # We do this for ALL messages so the user sees what they sent immediately.
    try:
        sb.table('chat_messages').insert({
            'content': message_content,
            'sender_id': current_user.id,
            'user_id': current_user.id,
            'session_id': room,
        }).execute()
        
        timestamp = datetime.utcnow().strftime('%H:%M')
        emit('receive_message', {
            'sender': current_user.username, 
            'content': message_content,
            'timestamp': timestamp
        }, room=room)
    except Exception as e:
        print(f"Error saving user message: {e}")
        return # If we can't save/broadcast user message, something is wrong.

    # --- 2. AI Processing ---
    # We respond to EVERYTHING now, acting as a tutor.
    print(f"Processing AI response for: {message_content}")
    
    # Import KeyManager locally to avoid circular import issues if any
    from .services.key_manager import key_manager
    
    # Simple retry loop for keys
    max_key_retries = 5 # Try up to 5 different keys/attempts
    key_attempts = 0
    success = False
    last_error = None
    
    while key_attempts < max_key_retries and not success:
        current_key = key_manager.get_current_key()
        if not current_key:
             emit('receive_message', {'sender': 'System', 'content': 'Error: Server is missing API Keys.', 'timestamp': timestamp}, room=room)
             return

        try:
            genai.configure(api_key=current_key)
            
            # List of models to try in order of preference
            # User requested 2.5-flash. 1.5-flash as backup.
            models_to_try = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']
            
            # --- A. Course Creation Command ---
            if "create course" in message_content.lower() and (":" in message_content or "about" in message_content):
                prompt = f"""You are a Master Content Creator. The user wants to create a course based on: '{message_content}'. 
                Generate a high-quality course structure in STRICT JSON format.
                {{
                  "title": "Course Title",
                  "description": "Short overview",
                  "lessons": [
                    {{"title": "Lesson 1", "content": "Full educational text content..."}},
                    {{"title": "Lesson 2", "content": "Full educational text content..."}}
                  ]
                }}
                Provide ONLY the JSON. No preamble."""
                
                for model_name in models_to_try:
                    try:
                        print(f"Attempting to generate course with {model_name} using key ...{current_key[-4:]}...")
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(prompt)
                        
                        raw_json = response.text.strip().replace('```json', '').replace('```', '')
                        course_data = json.loads(raw_json)
                        
                        # Insert Course
                        course_res = sb.table('courses').insert({
                            'title': course_data.get('title', 'Generated Course'),
                            'description': course_data.get('description', 'AI Generated'),
                            'author_id': current_user.id
                        }).execute()
                        
                        if course_res.data:
                            course_id = course_res.data[0]['id']
                            # Insert Lessons
                            for lesson in course_data.get('lessons', []):
                                sb.table('lessons').insert({
                                    'course_id': course_id,
                                    'title': lesson.get('title', 'Untitled'),
                                    'content': lesson.get('content', ''),
                                    'lesson_type': 'text'
                                }).execute()
                            
                            final_msg = f"✅ **Course Created!**\nCreated '{course_data.get('title')}' with {len(course_data.get('lessons', []))} lessons using {model_name}."
                        else:
                            final_msg = "❌ Failed to create course record."

                        # Send AI confirmation
                        emit('receive_message', {'sender': 'Autodidatic_AI', 'content': final_msg, 'timestamp': datetime.utcnow().strftime('%H:%M')}, room=room)
                        
                        # Save AI response
                        sb.table('chat_messages').insert({
                            'content': final_msg,
                            'sender_id': None, 'user_id': current_user.id, 'session_id': room
                        }).execute()
                        success = True
                        break # Break model loop
                        
                    except Exception as e:
                        print(f"Failed with {model_name}: {e}")
                        last_error = e
                        if "429" in str(e) or "Quota" in str(e):
                             # If quota error, stop trying models with THIS key, break to outer loop to rotate key
                             raise e 
                        continue # Try next model with same key

                if success: break # Break key loop
                
                # If we exhausted models without success but didn't raise 429, we probably failed generally.
                # But if we are here, we finished model loop.
                # If we didn't succeed, we should try rotating key?
                # Actually if it's not a 429, rotating key might not help, but let's try.
                raise last_error

            # --- B. Standard Tutor Chat ---
            else:
                system_instruction = """You are Autodidatic_AI, a helpful and encouraging expert tutor.
                
                IMPORTANT: Before answering, you must provide your internal monologue/reasoning enclosed in <thought> tags.
                Then provide the answer outside the tags.
                
                Example:
                User: Explain gravity.
                AI: <thought> The user is asking about gravity. I should explain it simply using an apple analogy. </thought>
                Gravity is the force that pulls things together...
                
                Keep responses concise unless asked for detail. Use markdown for the answer part."""
                
                for model_name in models_to_try:
                    try:
                        print(f"Attempting chat with {model_name} using key ...{current_key[-4:]}...")
                        chat_model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
                        response_stream = chat_model.generate_content(message_content, stream=True)
                        
                        full_ai_response = ""
                        full_thought = ""
                        emit('stream_start', {'sender': 'Autodidatic_AI'}, room=room)

                        thought_mode = False
                        
                        for chunk in response_stream:
                            if chunk.text:
                                text_chunk = chunk.text
                                
                                # Check for thought start
                                if "<thought>" in text_chunk:
                                    thought_mode = True
                                    parts = text_chunk.split("<thought>")
                                    if parts[0]: # Content before tag (unlikely if at start)
                                        emit('stream_chunk', {'chunk': parts[0]}, room=room)
                                        full_ai_response += parts[0]
                                    if len(parts) > 1:
                                        text_chunk = parts[1] # Remaining part starts inside thought
                                
                                # Check for thought end
                                if "</thought>" in text_chunk:
                                    thought_mode = False
                                    parts = text_chunk.split("</thought>")
                                    
                                    # Emission of the last thought part
                                    if parts[0]:
                                        emit('stream_thought', {'chunk': parts[0]}, room=room)
                                        full_thought += parts[0]
                                    
                                    # Content after tag (the answer starts here)
                                    if len(parts) > 1 and parts[1]:
                                        emit('stream_chunk', {'chunk': parts[1]}, room=room)
                                        full_ai_response += parts[1]
                                    
                                    continue # Processed both parts

                                # Standard processing based on mode
                                if thought_mode:
                                    emit('stream_thought', {'chunk': text_chunk}, room=room)
                                    full_thought += text_chunk
                                else:
                                    emit('stream_chunk', {'chunk': text_chunk}, room=room)
                                    full_ai_response += text_chunk
                        
                        emit('stream_end', {'timestamp': datetime.utcnow().strftime('%H:%M')}, room=room)
                        
                        # Save AI response to DB
                        sb.table('chat_messages').insert({
                            'content': full_ai_response.strip(),
                            'sender_id': None,
                            'user_id': current_user.id,
                            'session_id': room,
                        }).execute()
                        success = True
                        break # Break model loop
                        
                    except Exception as e:
                         print(f"Failed with {model_name}: {e}")
                         last_error = e
                         if "429" in str(e) or "Quota" in str(e):
                             raise e
                         continue # Try next model
                
                if success: break
                raise last_error

        except Exception as e:
            print(f"Key Attempt {key_attempts+1} Failed: {e}")
            if "429" in str(e) or "Quota" in str(e):
                 print("Quota exceeded, rotating key...")
                 key_manager.rotate_key()
                 key_attempts += 1
            else:
                 # If it's not a quota error (e.g. server error), maybe rotating won't help, but let's try a few times.
                 key_manager.rotate_key()
                 key_attempts += 1
    
    if not success:
        print(f"AI All Keys/Models Failed.")
        error_content = f"⚠️ AI Service Unavailable. All keys exhausted. Last Error: {str(last_error)}"
        emit('receive_message', {
            'sender': 'Autodidatic_AI', 'content': error_content,
            'timestamp': datetime.utcnow().strftime('%H:%M')
        }, room=room)
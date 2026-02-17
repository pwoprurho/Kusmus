import sys
from flask import Flask
from flask_bcrypt import Bcrypt
from kusmusapp.services.supabase_client import get_supabase
from dotenv import load_dotenv
import os

# Load env vars manually
load_dotenv()

def change_password(email, new_password):
    # Use a minimal Flask app context only for Bcrypt if needed, 
    # but Bcrypt can also be used directly.
    app = Flask(__name__)
    bcrypt = Bcrypt(app)
    
    with app.app_context():
        sb = get_supabase()
        
        # Hash the new password
        hashed_pw = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        try:
            # Update the user's password in the Supabase 'users' table
            result = sb.table('users').update({'password': hashed_pw}).eq('email', email).execute()
            
            # Check if any rows were updated
            if result.data:
                print(f"SUCCESS: Password for {email} has been updated.")
            else:
                print(f"ERROR: No user found with email {email}.")
                
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python change_password.py <email> <new_password>")
    else:
        email = sys.argv[1]
        password = sys.argv[2]
        change_password(email, password)

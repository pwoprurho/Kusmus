import os
import datetime
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from flask import url_for, session

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

class GoogleCalendarService:
    def __init__(self, credentials_path='credentials.json'):
        self.credentials_path = credentials_path

    def get_flow(self):
        flow = InstalledAppFlow.from_client_secrets_file(
            self.credentials_path, SCOPES)
        # The redirect_uri must match the one configured in the Google Cloud Console
        flow.redirect_uri = url_for('main.google_calendar_callback', _external=True)
        return flow

    def get_auth_url(self):
        flow = self.get_flow()
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url

    def fetch_token(self, code):
        flow = self.get_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials
        return credentials

    @staticmethod
    def create_event(credentials, title, description, start_time, end_time=None):
        service = build('calendar', 'v3', credentials=credentials)
        
        if end_time is None:
            # Default to 1 hour event
            end_time = (datetime.datetime.fromisoformat(start_time) + 
                       datetime.timedelta(hours=1)).isoformat()

        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'UTC',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 30},
                ],
            },
        }

        event = service.events().insert(calendarId='primary', body=event).execute()
        return event.get('htmlLink')

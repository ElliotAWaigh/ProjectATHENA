import datetime
import os.path
import requests

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)

        colours = {
            1 : "Light blue",
            2 : "Light green",
            3 : "Lavendar",
            4 : "Salmon",
            5 : "Yellow",
            6 : "Orange",
            7 : "Cyan",
            8 : "Gray",
            9 : "Blue",
            10 : "Green",
            11 : "Red",
        }

        event = {
            "summary" : "My Python Event",
            "location" : "Somewhere Online",
            "description" : "Some more details on this awesome event"
        }

        
    except HttpError as error:
        print("An error occured:", error)

def context_for_add_meeting():
    required_context = {
        "meeting_title": [],        # Open-ended
        "date_time": [],            # Open-ended
        "participants": [],         # Open-ended
        "duration": ["1hr", "2hrs", "3hrs"]  # Closed-ended options
    }
    optional_context = {
        "location": [],             # Open-ended
        "description": [],          # Open-ended
        "reminder_notification": ["1hr", "2hrs", "3hrs"] # Closed-ended options
    }
    open_ended_required = ["meeting_title", "date_time", "participants"]
    open_ended_optional = ["location", "description"]
    close_ended_required = ["duration"]
    close_ended_optional = ["reminder_notification"]

    # Combine all context definitions
    context_definitions = {**required_context, **optional_context}
    
    print("Context being sent:", required_context, optional_context, open_ended_required, open_ended_optional, close_ended_required, close_ended_optional)
    
    return required_context, optional_context, open_ended_required, open_ended_optional, close_ended_required, close_ended_optional




def action_for_add_meeting(context):
    print("Final context received:", context)  # Debug to see what context looks like at this point
    meeting_title = context.get("meeting_title", "Untitled Meeting")
    date_time = context.get("date_time", "unspecified time")
    participants = context.get("participants", "no participants")
    location = context.get("location", "no location")
    description = context.get("description", "no description")
    reminder_notification = context.get("reminder_notification", "no reminders")
    return f"The context is, {context}"
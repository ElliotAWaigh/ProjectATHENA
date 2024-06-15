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

def list_events():
    creds = None
    service = build("calendar", "v3", credentials=creds)

    now = datetime.datetime.now().isoformat() + "Z"

    event_result = service.events().list(calendarId="primary", timeMin=now, maxResults=10, singleEvents=True, orderBy="startTime").execute()
    events = event_result.get("items", [])

    if not events:
        print("None Found")
        return

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(start, event["summary"])



def context_for_add_meeting():
    required_context = {
        "meeting_title": [],
        "date_time": [],
        "participants": []
    }
    optional_context = {
        "location": [],
        "description": [],
        "reminder_notification": []
    }
    open_ended_required = ["meeting_title", "date_time", "participants"]
    open_ended_optional = ["location", "description", "reminder_notification"]
    return required_context, optional_context, open_ended_required, open_ended_optional

def context_for_remove_meeting():
    required_context = {
        "meeting_title": [],
        "date_time": []
    }
    optional_context = {}
    open_ended_required = ["meeting_title", "date_time"]
    open_ended_optional = []
    return required_context, optional_context, open_ended_required, open_ended_optional

def context_for_show_events_today():
    required_context = {
        "date": ["today"]
    }
    optional_context = {}
    open_ended_required = []
    open_ended_optional = []
    return required_context, optional_context, open_ended_required, open_ended_optional

def context_for_update_meeting():
    required_context = {
        "meeting_title": [],
        "date_time": []
    }
    optional_context = {
        "new_date_time": [],
        "participants": [],
        "location": [],
        "description": [],
        "reminder_notification": []
    }
    open_ended_required = ["meeting_title", "date_time"]
    open_ended_optional = ["new_date_time", "participants", "location", "description", "reminder_notification"]
    return required_context, optional_context, open_ended_required, open_ended_optional

def context_for_meeting_tomorrow():
    required_context = {
        "date": ["tomorrow"]
    }
    optional_context = {}
    open_ended_required = []
    open_ended_optional = []
    return required_context, optional_context, open_ended_required, open_ended_optional

def context_for_tomorrow():
    required_context = {
        "date": ["tomorrow"]
    }
    optional_context = {}
    open_ended_required = []
    open_ended_optional = []
    return required_context, optional_context, open_ended_required, open_ended_optional

def context_for_edit_meeting():
    required_context = {
        "meeting_title": [],
        "date_time": []
    }
    optional_context = {
        "new_date_time": [],
        "participants": [],
        "location": [],
        "description": [],
        "reminder_notification": []
    }
    open_ended_required = ["meeting_title", "date_time"]
    open_ended_optional = ["new_date_time", "participants", "location", "description", "reminder_notification"]
    return required_context, optional_context, open_ended_required, open_ended_optional

def action_for_add_meeting(context):
    meeting_title = context.get("meeting_title", "Untitled Meeting")
    date_time = context.get("date_time", "unspecified time")
    participants = context.get("participants", "no participants")
    location = context.get("location", "no location")
    description = context.get("description", "no description")
    reminder_notification = context.get("reminder_notification", "no reminders")
    return f"Adding meeting '{meeting_title}' on {date_time} with participants {participants}, location {location}, description '{description}', and reminders {reminder_notification}."

def action_for_remove_meeting(context):
    meeting_title = context.get("meeting_title", "Untitled Meeting")
    date_time = context.get("date_time", "unspecified time")
    return f"Removing meeting '{meeting_title}' scheduled on {date_time}."

def action_for_show_events_today(context):
    date = context.get("date", "today")
    time_range = context.get("time_range", "full day")
    return f"Showing events for {date} within the time range {time_range}."

def action_for_update_meeting(context):
    meeting_title = context.get("meeting_title", "Untitled Meeting")
    date_time = context.get("date_time", "unspecified time")
    new_date_time = context.get("new_date_time", date_time)
    participants = context.get("participants", "no participants")
    location = context.get("location", "no location")
    description = context.get("description", "no description")
    reminder_notification = context.get("reminder_notification", "no reminders")
    return f"Updating meeting '{meeting_title}' originally scheduled on {date_time} to new date and time {new_date_time}, with participants {participants}, location {location}, description '{description}', and reminders {reminder_notification}."

def action_for_meeting_tomorrow(context):
    date = context.get("date", "tomorrow")
    return f"Showing meetings scheduled for {date}."

def action_for_tomorrow(context):
    date = context.get("date", "tomorrow")
    return f"Showing events for {date}."

def action_for_edit_meeting(context):
    meeting_title = context.get("meeting_title", "Untitled Meeting")
    date_time = context.get("date_time", "unspecified time")
    new_date_time = context.get("new_date_time", date_time)
    participants = context.get("participants", "no participants")
    location = context.get("location", "no location")
    description = context.get("description", "no description")
    reminder_notification = context.get("reminder_notification", "no reminders")
    return f"Editing meeting '{meeting_title}' originally scheduled on {date_time} to new date and time {new_date_time}, with participants {participants}, location {location}, description '{description}', and reminders {reminder_notification}."
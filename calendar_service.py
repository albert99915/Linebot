"""Google Calendar 整合：將預約寫入 Google 日曆"""

import os
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

BASE_DIR = os.path.dirname(__file__)
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_calendar_service():
    """取得已授權的 Google Calendar 服務物件"""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def create_event(name, date_str, time_str, people, service, calendar_id=None):
    """
    在 Google Calendar 建立預約事件。

    回傳事件的 HTML 連結，或 None（未設定 Google Calendar 時）。
    """
    service_obj = get_calendar_service()
    if not service_obj:
        return None

    if not calendar_id:
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(hours=1)

    event = {
        "summary": f"預約 - {name} ({service})",
        "description": (
            f"姓名：{name}\n"
            f"人數：{people} 人\n"
            f"服務：{service}"
        ),
        "start": {
            "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Asia/Taipei",
        },
        "end": {
            "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Asia/Taipei",
        },
    }

    created = service_obj.events().insert(calendarId=calendar_id, body=event).execute()
    return created.get("htmlLink")

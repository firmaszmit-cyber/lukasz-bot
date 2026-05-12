import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import GOOGLE_CREDS_PATH, GOOGLE_TOKEN_PATH

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _load_credentials() -> Credentials:
    with open(GOOGLE_TOKEN_PATH) as f:
        token_data = json.load(f)

    # Token z MCP jest opakowany w {"normal": {...}}
    if "normal" in token_data:
        token_data = token_data["normal"]

    with open(GOOGLE_CREDS_PATH) as f:
        creds_data = json.load(f)
    client_config = creds_data.get("installed") or creds_data.get("web", {})

    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_config["client_id"],
        client_secret=client_config["client_secret"],
        scopes=SCOPES,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(token_data, creds)

    return creds


def _save_token(original: dict, creds: Credentials):
    updated = {**original, "access_token": creds.token}
    with open(GOOGLE_TOKEN_PATH, "w") as f:
        json.dump({"normal": updated}, f, indent=2)


def _get_service():
    return build("calendar", "v3", credentials=_load_credentials(), cache_discovery=False)


def add_event(title: str, start_iso: str, duration_minutes: int = 60, description: str = "") -> str:
    service = _get_service()

    start = datetime.fromisoformat(start_iso)
    if start.tzinfo is None:
        # Kraków = Europe/Warsaw, ale dla uproszczenia UTC+2 latem / UTC+1 zimą
        # Używamy offset z lokalnego czasu
        import time as _time
        offset = -_time.timezone if _time.daylight == 0 else -_time.altzone
        start = start.replace(tzinfo=timezone(timedelta(seconds=offset)))

    end = start + timedelta(minutes=duration_minutes)

    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }

    result = service.events().insert(calendarId="primary", body=event).execute()
    return result.get("htmlLink", "Wydarzenie dodane")


def list_events(days: int = 7) -> list:
    service = _get_service()
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=20,
    ).execute()

    events = []
    for e in result.get("items", []):
        start = e["start"].get("dateTime") or e["start"].get("date")
        events.append({"title": e.get("summary", "(bez tytułu)"), "start": start})
    return events

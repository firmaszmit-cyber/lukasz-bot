import base64
import json
import logging
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import GMAIL_USER, GOOGLE_CREDS_PATH, GOOGLE_TOKEN_PATH

logger = logging.getLogger(__name__)

# Musi być zgodne ze scopami w tokenie — patrz reauth_google.py
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _load_credentials() -> Credentials:
    with open(GOOGLE_TOKEN_PATH) as f:
        token_data = json.load(f)

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

    return creds


def send_email(to: str, subject: str, body: str, attachment_path: str = None) -> str:
    msg = MIMEMultipart()
    msg["From"] = f"SzmitRemont <{GMAIL_USER}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path:
        p = Path(attachment_path)
        if p.exists():
            with open(p, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{p.name}"')
            msg.attach(part)
            logger.info("Załącznik: %s", p.name)
        else:
            logger.warning("Plik załącznika nie istnieje: %s", attachment_path)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    result = service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()

    logger.info("Email wysłany do %s | ID: %s", to, result.get("id"))
    attachment_info = f" + załącznik {Path(attachment_path).name}" if attachment_path else ""
    return f"Email wysłany do {to}{attachment_info}"

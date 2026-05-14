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
    "https://www.googleapis.com/auth/gmail.readonly",
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


def read_emails(query: str = "", max_results: int = 5) -> str:
    """Pobiera wiadomości ze skrzynki Gmail pasujące do zapytania."""
    import base64
    import re

    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    results = service.users().messages().list(
        userId="me",
        q=query or "in:inbox",
        maxResults=max_results,
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        return f"Brak wiadomości pasujących do: '{query}'."

    output_parts = []
    for msg in messages:
        msg_data = service.users().messages().get(
            userId="me", id=msg["id"], format="full",
        ).execute()

        headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(brak tematu)")
        sender = headers.get("From", "(nieznany nadawca)")
        date_str = headers.get("Date", "")

        body = ""
        payload = msg_data.get("payload", {})
        parts = payload.get("parts", [])
        if parts:
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                        break
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        body_preview = body.strip()[:500].replace("\r\n", "\n") if body else "(brak treści)"

        output_parts.append(
            f"Od: {sender}\nData: {date_str}\nTemat: {subject}\n---\n{body_preview}"
        )

    return "\n\n===\n\n".join(output_parts)


def search_email_address(name: str) -> str:
    """Szuka adresu email osoby w historii skrzynki Gmail."""
    import re

    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    results = service.users().messages().list(
        userId="me",
        q=name,
        maxResults=20,
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        return f"Nie znaleziono wiadomości dla '{name}'."

    candidates: dict[str, str] = {}  # email -> display name
    name_parts = [p.lower() for p in name.split() if len(p) > 2]

    for msg in messages[:10]:
        msg_data = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "To"],
        ).execute()

        for header in msg_data.get("payload", {}).get("headers", []):
            if header["name"] not in ("From", "To"):
                continue
            value = header["value"]
            if GMAIL_USER in value:
                continue
            if not any(part in value.lower() for part in name_parts):
                continue
            match = re.search(r'[\w.+\-]+@[\w\-]+\.[\w.]+', value)
            if match:
                email = match.group(0)
                display = re.sub(r'<.*?>', '', value).strip().strip('"\'')
                candidates[email] = display or email

    if not candidates:
        return f"Nie znaleziono adresu email dla '{name}' w skrzynce."

    lines = [f"{display} <{email}>" if display != email else email
             for email, display in list(candidates.items())[:5]]
    return "Znalezione adresy:\n" + "\n".join(lines)

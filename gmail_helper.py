import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import GMAIL_APP_PASSWORD, GMAIL_USER

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str, attachment_path: str = None) -> str:
    if not GMAIL_APP_PASSWORD:
        raise RuntimeError("Brak GMAIL_APP_PASSWORD w .env — skonfiguruj hasło aplikacji Google.")

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

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    logger.info("Email wysłany do %s | temat: %s", to, subject)
    attachment_info = f" + załącznik {Path(attachment_path).name}" if attachment_path else ""
    return f"Email wysłany do {to}{attachment_info}"

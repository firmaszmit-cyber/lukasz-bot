"""
Uruchom lokalnie raz, żeby uzyskać token z kalendarzem + gmail.send.
Wynik: nowy plik token_new.json + zakodowany GOOGLE_TOKEN_B64 do Railway.
"""
import base64
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

CREDS_PATH = Path.home() / ".calendar-mcp/credentials.json"
TOKEN_OUT = Path("token_new.json")

flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
creds = flow.run_local_server(port=0)

token_data = {
    "normal": {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
}

TOKEN_OUT.write_text(json.dumps(token_data, indent=2))
print(f"Token zapisany: {TOKEN_OUT}")

b64 = base64.b64encode(json.dumps(token_data).encode()).decode()
print("\n=== GOOGLE_TOKEN_B64 (wklej do Railway Variables) ===")
print(b64)

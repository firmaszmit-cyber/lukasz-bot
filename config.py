import base64
import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])

GMAIL_USER = os.getenv("GMAIL_USER", "firmaszmit@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# Google credentials — lokalnie z pliku, na Railway z env var (base64 JSON)
def _write_temp_json(env_var: str, fallback_path: str) -> str:
    raw = os.getenv(env_var)
    if raw:
        data = json.loads(base64.b64decode(raw).decode())
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
        json.dump(data, tmp)
        tmp.flush()
        return tmp.name
    return fallback_path

GOOGLE_CREDS_PATH = _write_temp_json(
    "GOOGLE_CREDENTIALS_B64",
    os.getenv("GOOGLE_CREDS_PATH", str(Path.home() / ".calendar-mcp/credentials.json"))
)
GOOGLE_TOKEN_PATH = _write_temp_json(
    "GOOGLE_TOKEN_B64",
    os.getenv("GOOGLE_TOKEN_PATH", str(Path.home() / ".calendar-mcp/mcp-google-calendar-token.json"))
)

# Ścieżki do plików — lokalnie Desktop, na Railway /tmp
_is_railway = bool(os.getenv("RAILWAY_ENVIRONMENT"))
_base = Path("/tmp") if _is_railway else Path.home() / "Desktop/SzmitRemonty"

NOTES_DIR = Path(os.getenv("NOTES_DIR", str(_base / "Wnioski")))
KLIENCI_DIR = Path(os.getenv("KLIENCI_DIR", str(_base / "Klienci")))
CENNIK_PATH = Path(os.getenv("CENNIK_PATH", str(Path(__file__).parent / "cennik.md")))

NOTES_DIR.mkdir(parents=True, exist_ok=True)
KLIENCI_DIR.mkdir(parents=True, exist_ok=True)

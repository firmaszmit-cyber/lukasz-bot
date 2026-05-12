import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def transcribe(audio_path: str) -> str:
    from openai import OpenAI
    from config import OPENAI_API_KEY

    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="pl",
        )
    text = result.text.strip()
    logger.info("Transkrypcja: %s", text[:100])
    return text

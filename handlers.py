import base64
import logging
import os
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from claude_client import process_message
from config import ALLOWED_USER_ID

logger = logging.getLogger(__name__)

PENDING_EMAILS: dict[int, dict] = {}


def _is_allowed(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_USER_ID


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.reply_text(
        "Cześć Łukasz! Możesz pisać lub wysyłać głosówki.\n\n"
        "Co mogę:\n"
        "📅 Dodać do kalendarza — np. 'dodaj w czwartek o 9 wizyta u Nowaka'\n"
        "💰 Wycena — np. 'wycena: łazienka 6m², 3 punkty wod-kan, płytki 15m²'\n"
        "📝 Notatka — np. 'notatka: ustalenia ze spotkania z Kowalskim'\n"
        "📢 Post FB — np. 'zrób post o remoncie łazienki w Krakowie'\n"
        "💬 Cokolwiek innego — po prostu napisz"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    await _process_and_reply(update, update.message.text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    await update.message.reply_text("Transkrybuję głosówkę...")

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await file.download_to_drive(tmp_path)
        from whisper_helper import transcribe
        text = transcribe(tmp_path)
        await update.message.reply_text(f"_Usłyszałem:_ {text}", parse_mode="Markdown")
        await _process_and_reply(update, text)
    except Exception as e:
        logger.error("Błąd głosówki: %s", e, exc_info=True)
        await update.message.reply_text(f"❌ Błąd transkrypcji: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.chat.send_action(ChatAction.TYPING)

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()
    image_base64 = base64.b64encode(photo_bytes).decode("utf-8")

    caption = update.message.caption or "Co widzisz na zdjęciu? Jeśli to dane do wyceny, przygotuj kosztorys."
    await _process_and_reply(update, caption, image_base64=image_base64)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if query.data == "email_yes":
        email_data = PENDING_EMAILS.pop(user_id, None)
        if not email_data:
            await query.edit_message_text("Brak oczekującego emaila.")
            return
        from tools_executor import execute_tool
        result = execute_tool("send_email", email_data)
        await query.edit_message_text(f"✅ {result}")

    elif query.data == "email_no":
        PENDING_EMAILS.pop(user_id, None)
        await query.edit_message_text("❌ Wysyłka anulowana.")


async def _process_and_reply(update: Update, text: str, image_base64: str = None):
    try:
        user_id = update.effective_user.id
        reply, pending_email = process_message(text, image_base64=image_base64, user_id=user_id)

        # Wyślij wygenerowany XLSX na Telegram
        from tools_executor import pop_generated_files
        for file_path in pop_generated_files():
            p = Path(file_path)
            if p.exists():
                await update.message.reply_document(
                    document=p.open("rb"),
                    filename=p.name,
                    caption="📊 Kosztorys XLSX"
                )

        if pending_email:
            user_id = update.effective_user.id
            PENDING_EMAILS[user_id] = pending_email
            to = pending_email.get("to", "?")
            subject = pending_email.get("subject", "")
            body = pending_email.get("body", "")
            attachment = pending_email.get("attachment_path")
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Tak, wyślij", callback_data="email_yes"),
                InlineKeyboardButton("❌ Anuluj", callback_data="email_no"),
            ]])
            preview = (
                f"📧 *Podgląd maila*\n"
                f"*Do:* {to}\n"
                f"*Temat:* {subject}\n\n"
                f"{body}"
            )
            if attachment:
                preview += f"\n\n📎 Załącznik: {Path(attachment).name}"
            preview += "\n\n─────────────────\nWysłać?"
            # Telegram limit 4096 znaków
            if len(preview) > 4096:
                preview = preview[:4090] + "…"
            await update.message.reply_text(preview, parse_mode="Markdown", reply_markup=keyboard)
        else:
            if len(reply) <= 4096:
                await update.message.reply_text(reply)
            else:
                for chunk in [reply[i:i + 4096] for i in range(0, len(reply), 4096)]:
                    await update.message.reply_text(chunk)

    except Exception as e:
        logger.error("Błąd przetwarzania: %s", e, exc_info=True)
        await update.message.reply_text(f"Błąd: {e}")

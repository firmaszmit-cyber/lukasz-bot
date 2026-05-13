import logging
from datetime import date
from pathlib import Path
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY, CENNIK_PATH

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CENNIK_TEXT = CENNIK_PATH.read_text(encoding="utf-8") if CENNIK_PATH.exists() else ""

SYSTEM_PROMPT = f"""Jesteś osobistym asystentem Łukasza Szmita.

Łukasz prowadzi dwie działalności:
- **SzmitRemont** — firma remontowo-wykończeniowa, Kraków, tel. +48 692 238 159, firmaszmit@gmail.com
- **AI Studio.Crafts** — wdrożenia systemów AI dla małych firm usługowych

Dzisiaj jest {date.today().strftime('%d.%m.%Y')}.

Rozmawiasz po polsku. Odpowiedzi są krótkie i konkretne.

## Możesz:
1. Dodać wydarzenie do kalendarza Google
2. Wygenerować kosztorys na podstawie cennika
3. Wysłać email (np. z kosztorysem do klienta)
4. Zapisać notatkę do pliku
5. Stworzyć post na Facebook

## Wysyłka wyceny mailem — pełny przepływ:
Gdy użytkownik poprosi o wycenę I podał adres email lub imię klienta:
1. Jeśli nie ma adresu email — wywołaj `find_email_address` z imieniem/nazwiskiem klienta
2. Jeśli znalazłeś adres — zapytaj użytkownika czy to ten właściwy przed wysyłką
Gdy użytkownik potwierdził adres lub podał go ręcznie:
1. Wywołaj `generate_wycena` → dostaniesz kosztorys tekstowy i linię PLIK_XLSX=/ścieżka/do/pliku.xlsx
2. Wywołaj `send_email` z:
   - to: adres z zapytania
   - subject: "Kosztorys SzmitRemont – [imię klienta]"
   - body: krótkie przywitanie + informacja że kosztorys w załączniku + podpis Łukasza
   - attachment_path: ścieżka z linii PLIK_XLSX= (jeśli jest)
Uwaga: wysyłka wymaga potwierdzenia użytkownika — zostanie pokazany przycisk.

## Termin realizacji:
Jeśli przy wycenie podano termin (np. "do 30 czerwca", "termin: 15.07"), dodatkowo wywołaj `add_calendar_event`:
- title: "Start prac — [klient]"
- start_iso: podana data o 8:00

## Cennik SzmitRemont (robocizna, bez materiałów):

{CENNIK_TEXT}

Przy wycenie: używaj dokładnych stawek z cennika. Przy zakresach (np. 30–50 zł/m²) podaj oba końce.
"""

TOOLS = [
    {
        "name": "add_calendar_event",
        "description": "Dodaj wydarzenie do Google Calendar użytkownika",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tytuł wydarzenia"},
                "start_iso": {"type": "string", "description": "Data i godzina ISO 8601, np. '2026-05-15T09:00:00'"},
                "duration_minutes": {"type": "integer", "description": "Czas trwania w minutach (domyślnie 60)"},
                "description": {"type": "string", "description": "Dodatkowy opis"},
            },
            "required": ["title", "start_iso"],
        },
    },
    {
        "name": "generate_wycena",
        "description": "Wygeneruj kosztorys dla klienta na podstawie cennika SzmitRemont",
        "input_schema": {
            "type": "object",
            "properties": {
                "klient": {"type": "string", "description": "Imię lub nazwa klienta"},
                "prace": {
                    "type": "array",
                    "description": "Lista prac do wyceny",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nazwa": {"type": "string"},
                            "ilosc": {"type": "number"},
                            "jednostka": {"type": "string"},
                            "stawka_min": {"type": "number"},
                            "stawka_max": {"type": "number"},
                        },
                        "required": ["nazwa", "ilosc", "jednostka", "stawka_min"],
                    },
                },
            },
            "required": ["prace"],
        },
    },
    {
        "name": "send_email",
        "description": "Wyślij email z konta firmaszmit@gmail.com",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Adres odbiorcy"},
                "subject": {"type": "string", "description": "Temat wiadomości"},
                "body": {"type": "string", "description": "Treść maila (plain text)"},
                "attachment_path": {"type": "string", "description": "Ścieżka do pliku XLSX z kosztorysem (z wyniku generate_wycena)"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "save_note",
        "description": "Zapisz notatkę do pliku na dysku",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Krótki tytuł notatki"},
                "content": {"type": "string", "description": "Treść notatki w formacie markdown"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "find_email_address",
        "description": "Znajdź adres email klienta przeszukując historię skrzynki Gmail",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Imię i/lub nazwisko klienta, np. 'Adam Winiarski'"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "generate_fb_post",
        "description": "Stwórz gotowy post na Facebook dla SzmitRemont lub AI Studio.Crafts",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Gotowy tekst posta"},
                "typ": {
                    "type": "string",
                    "enum": ["realizacja", "oferta", "ai_studio"],
                    "description": "'realizacja', 'oferta' lub 'ai_studio'",
                },
            },
            "required": ["content", "typ"],
        },
    },
]


def process_message(user_text: str, image_base64: str = None) -> tuple[str, Optional[dict]]:
    """
    Uruchamia pętlę agentową. send_email jest przechwytywany — nie wykonuje się
    automatycznie, wraca jako pending_email do potwierdzenia przez użytkownika.
    Zwraca (tekst_odpowiedzi, pending_email_lub_None).
    """
    from tools_executor import execute_tool

    if image_base64:
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64},
            },
            {"type": "text", "text": user_text},
        ]
    else:
        content = user_text

    messages = [{"role": "user", "content": content}]
    final_text = ""
    pending_email = None

    for _ in range(6):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        final_text = "\n".join(b.text for b in response.content if b.type == "text").strip()

        if not tool_blocks or response.stop_reason == "end_turn":
            break

        tool_results = []
        for tb in tool_blocks:
            if tb.name == "send_email":
                pending_email = tb.input
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tb.id,
                    "content": "Email czeka na potwierdzenie użytkownika.",
                })
            else:
                logger.info("Tool: %s", tb.name)
                result = execute_tool(tb.name, tb.input)
                tool_results.append({"type": "tool_result", "tool_use_id": tb.id, "content": result})

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return final_text or "Gotowe.", pending_email

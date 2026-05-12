import logging
from datetime import date
from pathlib import Path

from config import KLIENCI_DIR, NOTES_DIR

logger = logging.getLogger(__name__)

GENERATED_FILES: list[str] = []


def pop_generated_files() -> list[str]:
    files = list(GENERATED_FILES)
    GENERATED_FILES.clear()
    return files


def execute_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "add_calendar_event":
        return _add_calendar_event(**tool_input)
    elif tool_name == "generate_wycena":
        return _generate_wycena(**tool_input)
    elif tool_name == "send_email":
        return _send_email(**tool_input)
    elif tool_name == "save_note":
        return _save_note(**tool_input)
    elif tool_name == "generate_fb_post":
        return _generate_fb_post(**tool_input)
    else:
        return f"Nieznane narzędzie: {tool_name}"


def _add_calendar_event(title: str, start_iso: str, duration_minutes: int = 60, description: str = "") -> str:
    from google_calendar import add_event
    try:
        link = add_event(title, start_iso, duration_minutes, description)
        return f"Dodano do kalendarza: {title}\n{link}"
    except Exception as e:
        logger.error("Błąd kalendarza: %s", e)
        return f"Błąd dodawania do kalendarza: {e}"


def _generate_wycena(prace: list[dict], klient: str = "") -> str:
    lines = []
    total_min = 0.0
    total_max = 0.0

    header = f"KOSZTORYS — SzmitRemont\nKlient: {klient}\n" if klient else "KOSZTORYS — SzmitRemont\n"
    lines.append(header)
    lines.append(f"{'Lp.':<4} {'Praca':<40} {'Ilość':<10} {'Jedn.':<8} {'Min (zł)':<10} {'Max (zł)':<10}")
    lines.append("-" * 85)

    for i, p in enumerate(prace, 1):
        ilosc = p["ilosc"]
        stawka_min = p["stawka_min"]
        stawka_max = p.get("stawka_max", stawka_min)
        wartosc_min = ilosc * stawka_min
        wartosc_max = ilosc * stawka_max
        total_min += wartosc_min
        total_max += wartosc_max
        lines.append(
            f"{i:<4} {p['nazwa']:<40} {ilosc:<10.1f} {p['jednostka']:<8} {wartosc_min:<10.0f} {wartosc_max:<10.0f}"
        )

    lines.append("-" * 85)
    if total_min == total_max:
        lines.append(f"SUMA ROBOCIZNA: {total_min:.0f} zł")
    else:
        lines.append(f"SUMA ROBOCIZNA: {total_min:.0f} – {total_max:.0f} zł")
    lines.append("\nCeny dotyczą robocizny. Materiały po stronie klienta.")
    lines.append("Gwarancja 24 miesiące. Tel. +48 692 238 159")

    # Generuj XLSX
    try:
        from kosztorys_builder import build_xlsx
        slug = klient.replace(" ", "_").replace("/", "-") if klient else "klient"
        xlsx_path = str(KLIENCI_DIR / slug / f"kosztorys_{slug}_{date.today().isoformat()}.xlsx")
        build_xlsx(klient, prace, xlsx_path)
        GENERATED_FILES.append(xlsx_path)
        lines.append(f"\nPLIK_XLSX={xlsx_path}")
    except Exception as e:
        logger.warning("Nie udało się wygenerować XLSX: %s", e)

    return "\n".join(lines)


def _send_email(to: str, subject: str, body: str, attachment_path: str = None) -> str:
    from gmail_helper import send_email
    try:
        return send_email(to, subject, body, attachment_path=attachment_path)
    except Exception as e:
        logger.error("Błąd wysyłki maila: %s", e)
        return f"Błąd wysyłki maila: {e}"


def _save_note(title: str, content: str) -> str:
    slug = title.lower().replace(" ", "_").replace("/", "-")[:50]
    filename = f"{date.today().isoformat()}_{slug}.md"
    path = NOTES_DIR / filename
    path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    return f"Notatka zapisana: {path.name}"


def _generate_fb_post(content: str, typ: str) -> str:
    return content

from io import BytesIO
import os

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .library import download_sheet_pdf


BLUE = (0.035, 0.16, 0.39)


def _register_word_like_font() -> str:
    candidates = [
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", "LiberationSans"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "LiberationSans"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans"),
    ]

    for path, name in candidates:
        if os.path.exists(path):
            try:
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                pass

    return "Helvetica"


WORD_LIKE_FONT = _register_word_like_font()


def _text_width(text: str, font_name: str, font_size: float, c: canvas.Canvas) -> float:
    return c.stringWidth(text, font_name, font_size)


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float, c: canvas.Canvas):
    words = (text or "").split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(candidate, font_name, font_size, c) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_title(text: str, base_size: float, min_size: float, max_width: float, c: canvas.Canvas):
    font_name = WORD_LIKE_FONT
    size = base_size

    while size > min_size:
        lines = _wrap_text(text, font_name, size, max_width, c)
        if len(lines) <= 3 and all(
            _text_width(line, font_name, size, c) <= max_width
            for line in lines
        ):
            return font_name, size, lines
        size -= 1

    return font_name, min_size, _wrap_text(text, font_name, min_size, max_width, c)


def create_title_page(title: str, title_type: str, font_size_override=None) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    is_main = title_type == "Titre principal"
    display_text = (title or "").strip()
    if is_main:
        display_text = display_text.upper()

    max_width = width - 95
    base_size = 40 if is_main else 27
    min_size = 23 if is_main else 18

    if font_size_override is not None:
        try:
            chosen_size = max(12, min(72, float(font_size_override)))
        except (TypeError, ValueError):
            chosen_size = None
    else:
        chosen_size = None

    if chosen_size is not None:
        font_name = WORD_LIKE_FONT
        font_size = chosen_size
        lines = _wrap_text(display_text, font_name, font_size, max_width, c)
    else:
        font_name, font_size, lines = _fit_title(
            display_text,
            base_size=base_size,
            min_size=min_size,
            max_width=max_width,
            c=c,
        )

    c.setFillColorRGB(*BLUE)
    c.setStrokeColorRGB(*BLUE)
    c.setLineWidth(1.35 if is_main else 1.0)
    c.setFont(font_name, font_size)

    line_gap = font_size * 1.22
    block_height = (len(lines) - 1) * line_gap
    center_y = height * 0.54
    start_y = center_y + block_height / 2

    for idx, line in enumerate(lines):
        y = start_y - idx * line_gap
        text_width = c.stringWidth(line, font_name, font_size)
        x = (width - text_width) / 2
        c.drawString(x, y, line)

        underline_y = y - max(3.0, font_size * 0.10)
        c.line(x, underline_y, x + text_width, underline_y)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def build_dossier_pdf(items: list[dict]) -> bytes:
    writer = PdfWriter()

    for item in items:
        item_type = item.get("Type")

        if item_type in ("Titre principal", "Sous-titre"):
            page_pdf = create_title_page(
                item.get("Désignation", ""),
                item_type,
                item.get("font_size"),
            )
            reader = PdfReader(BytesIO(page_pdf))
            for page in reader.pages:
                writer.add_page(page)
            continue

        if item_type == "FT":
            sheet_id = item.get("technical_sheet_id")
            if not sheet_id:
                raise ValueError(
                    f"Fiche non associée : {item.get('Désignation', '')}"
                )

            pdf_bytes = download_sheet_pdf(sheet_id)
            reader = PdfReader(BytesIO(pdf_bytes))

            # Les pages de la fiche fabricant sont reprises directement.
            # Aucun contenu n'est redessiné, recadré ou recréé.
            for page in reader.pages:
                writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output.getvalue()

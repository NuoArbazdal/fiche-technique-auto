import re
from pathlib import Path
from io import BytesIO
from pypdf import PdfReader
from .text_utils import normalize_text

KNOWN_BRANDS = [
    "Forbo", "Tarkett", "Gerflor", "Unikalo", "Sika",
    "Knauf", "Siniat", "Weber", "Bostik", "Mapei"
]

CATEGORY_HINTS = {
    "sol pvc": ["pvc", "vinyle", "flooring", "sol souple"],
    "peinture": ["peinture", "paint", "velours", "satin", "mat"],
    "colle": ["colle", "adhesive"],
    "ragréage": ["ragréage", "ragreage", "smoothing compound"],
    "plafond": ["plafond", "ceiling"],
}

def extract_first_pages_text(pdf_bytes: bytes, max_pages: int = 3) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    chunks = []
    for page in reader.pages[:max_pages]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)

def _clean_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem

def detect_brand(text: str, filename: str = "") -> str:
    haystack = f"{filename}\n{text}".lower()
    for brand in KNOWN_BRANDS:
        if brand.lower() in haystack:
            return brand
    return ""

def detect_category(text: str) -> str:
    normalized = normalize_text(text)
    for category, hints in CATEGORY_HINTS.items():
        if any(normalize_text(hint) in normalized for hint in hints):
            return category
    return ""

def detect_reference(text: str) -> str:
    patterns = [
        r"(?im)^(?:référence|reference|ref\.?)[\s:]+([^\n]{2,80})$",
        r"(?im)^(?:code produit|product code)[\s:]+([^\n]{2,80})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""

def suggest_aliases(product_name: str) -> list[str]:
    aliases = []
    words = product_name.split()
    if len(words) >= 3:
        aliases.append(" ".join(words[:-1]))
        aliases.append(" ".join(words[1:]))
    return list(dict.fromkeys(a for a in aliases if len(a) >= 4))

def detect_metadata(filename: str, pdf_bytes: bytes) -> dict:
    text = extract_first_pages_text(pdf_bytes)
    product_name = _clean_filename(filename)

    # Le nom du fichier reste la source la plus sûre pour la V1.
    # Les informations extraites du PDF servent de proposition et restent validables.
    return {
        "product_name": product_name,
        "brand": detect_brand(text, filename),
        "category": detect_category(text),
        "reference": detect_reference(text),
        "version_label": "",
        "aliases": suggest_aliases(product_name),
        "extracted_text": text[:6000],
    }

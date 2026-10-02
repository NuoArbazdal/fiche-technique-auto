import re
from pathlib import Path
from io import BytesIO

from pypdf import PdfReader

from .text_utils import normalize_text


KNOWN_BRANDS = [
    "Forbo", "Tarkett", "Gerflor", "Unikalo", "Sika", "Knauf", "Siniat",
    "Weber", "Bostik", "Mapei", "Zolpan", "Seigneurie", "Tollens",
    "Sto", "Caparol", "Parexlanko", "Uzin", "Mapei", "Soprema",
]

CATEGORY_HINTS = {
    "sol pvc": ["pvc", "vinyle", "flooring", "sol souple", "linoleum", "linoléum"],
    "peinture": ["peinture", "paint", "velours", "satin", "mat", "laque"],
    "colle": ["colle", "adhesive", "adhésif"],
    "ragréage": ["ragréage", "ragreage", "smoothing compound", "enduit de sol"],
    "primaire": ["primaire", "primer"],
    "plafond": ["plafond", "ceiling", "dalle acoustique"],
    "enduit": ["enduit", "filler", "rebouchage", "lissage"],
    "résine": ["résine", "resine", "epoxy", "époxy", "polyuréthane"],
}

NOISE_PATTERNS = [
    r"\bfiche\s+technique\b",
    r"\bfiche\s+produit\b",
    r"\bfiche\s+de\s+donn[eé]es\b",
    r"\btechnical\s+data\s+sheet\b",
    r"\bproduct\s+data\s+sheet\b",
    r"\bdata\s+sheet\b",
    r"\bfts?\b",
    r"\btds\b",
    r"\bversion\s*\d+(?:[._-]\d+)*\b",
    r"\bind(?:ice)?\s*[a-z0-9]+\b",
    r"\brev(?:ision)?\s*[a-z0-9]+\b",
    r"\bmaj\s*\d{2,4}\b",
]

DATE_PATTERNS = [
    r"\b(20\d{2}[-_.](?:0?[1-9]|1[0-2])(?:[-_.](?:0?[1-9]|[12]\d|3[01]))?)\b",
    r"\b((?:0?[1-9]|1[0-2])[-_.]20\d{2})\b",
    r"\b(20\d{2})\b",
]


def extract_first_pages_text(pdf_bytes: bytes, max_pages: int = 3) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    chunks = []
    for page in reader.pages[:max_pages]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def _clean_filename(filename: str) -> str:
    stem = Path(filename).stem

    stem = re.sub(r"^[\s\-_]*(?:\d{1,4}[\s\-_.)]+)+", "", stem)
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s*-\s*", " ", stem)

    for pattern in NOISE_PATTERNS:
        stem = re.sub(pattern, " ", stem, flags=re.IGNORECASE)

    stem = re.sub(r"\b(?:fr|fra|french|uk|en|anglais)\b$", " ", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+", " ", stem).strip(" ._-")

    return stem or Path(filename).stem


def detect_brand(text: str, filename: str = "") -> str:
    haystack = normalize_text(f"{filename}\n{text}")
    for brand in KNOWN_BRANDS:
        if normalize_text(brand) in haystack:
            return brand
    return ""


def detect_category(text: str, filename: str = "") -> str:
    normalized = normalize_text(f"{filename}\n{text}")
    best_category = ""
    best_hits = 0

    for category, hints in CATEGORY_HINTS.items():
        hits = sum(1 for hint in hints if normalize_text(hint) in normalized)
        if hits > best_hits:
            best_hits = hits
            best_category = category

    return best_category


def detect_reference(text: str) -> str:
    patterns = [
        r"(?im)^(?:référence|reference|ref\.?)[\s:№n°#-]+([^\n]{2,80})$",
        r"(?im)^(?:code produit|product code|article|code article)[\s:№n°#-]+([^\n]{2,80})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
            if len(value) <= 80:
                return value
    return ""


def detect_version(text: str, filename: str = "") -> str:
    source = f"{filename}\n{text[:2500]}"

    version_match = re.search(
        r"(?im)\b(?:version|révision|revision|indice|index)\s*[:#-]?\s*([a-z0-9][a-z0-9._/-]{0,20})",
        source,
    )
    if version_match:
        return version_match.group(1).strip()

    for pattern in DATE_PATTERNS:
        match = re.search(pattern, source)
        if match:
            return match.group(1)

    return ""


def suggest_aliases(product_name: str, brand: str = "") -> list[str]:
    aliases = []
    clean = re.sub(r"\s+", " ", product_name).strip()

    if clean:
        aliases.append(clean)

    words = clean.split()
    if len(words) >= 3:
        aliases.append(" ".join(words[:-1]))
        aliases.append(" ".join(words[1:]))

    if brand:
        brand_norm = normalize_text(brand)
        without_brand = " ".join(
            word for word in words
            if normalize_text(word) != brand_norm
        ).strip()
        if without_brand and normalize_text(without_brand) != normalize_text(clean):
            aliases.append(without_brand)

    simplified = re.sub(
        r"\b(?:mat|satin|velours|brillant|blanc|base|intérieur|interieur|extérieur|exterieur)\b",
        " ",
        clean,
        flags=re.IGNORECASE,
    )
    simplified = re.sub(r"\s+", " ", simplified).strip()
    if len(simplified) >= 4 and normalize_text(simplified) != normalize_text(clean):
        aliases.append(simplified)

    unique = []
    seen = set()
    for alias in aliases:
        normalized = normalize_text(alias)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(alias)

    return unique


def detect_metadata(filename: str, pdf_bytes: bytes) -> dict:
    text = extract_first_pages_text(pdf_bytes)
    product_name = _clean_filename(filename)
    brand = detect_brand(text, filename)

    return {
        "product_name": product_name,
        "brand": brand,
        "category": detect_category(text, filename),
        "reference": detect_reference(text),
        "version_label": detect_version(text, filename),
        "aliases": suggest_aliases(product_name, brand),
        "extracted_text": text[:6000],
    }

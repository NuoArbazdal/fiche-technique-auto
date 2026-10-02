import re
from .matcher import search_library

def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\\s+", " ", raw).strip(" \\t-•")
        if not line:
            continue
        if len(line) < 2:
            continue
        lines.append(line)
    return lines

def _looks_like_title(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    return (
        upper_ratio >= 0.8
        or line.endswith(":")
        or (len(line.split()) <= 7 and len(line) <= 70 and line == line.title())
    )

def analyze_description(text: str, sheets: list[dict]) -> list[dict]:
    rows = []
    for index, line in enumerate(_clean_lines(text), start=1):
        matches = search_library(line, sheets, limit=1) if sheets else []
        score = matches[0][0] if matches else 0
        sheet = matches[0][1] if matches else None

        if sheet and score >= 88:
            kind = "Produit"
            status = "Trouvé"
        elif sheet and score >= 70:
            kind = "À vérifier"
            status = "Correspondance possible"
        elif _looks_like_title(line):
            kind = "Titre"
            status = ""
        else:
            kind = "À vérifier"
            status = "Aucune fiche fiable"

        rows.append({
            "Ordre": index,
            "Texte du descriptif": line,
            "Type": kind,
            "Fiche proposée": sheet.get("product_name", "") if sheet else "",
            "Marque": sheet.get("brand", "") if sheet else "",
            "Score": score if sheet else 0,
            "Statut": status,
            "technical_sheet_id": sheet.get("id") if sheet else None,
        })
    return rows

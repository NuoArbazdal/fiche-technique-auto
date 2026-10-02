from rapidfuzz import fuzz
from .text_utils import normalize_text

def score_query(query: str, sheet: dict) -> int:
    q = normalize_text(query)
    candidates = [sheet.get("product_name", "")]
    candidates.extend(sheet.get("aliases", []) or [])
    scores = [
        fuzz.token_set_ratio(q, normalize_text(candidate))
        for candidate in candidates
        if candidate
    ]
    return int(max(scores) if scores else 0)

def search_library(query: str, sheets: list[dict], limit: int = 5):
    ranked = [(score_query(query, sheet), sheet) for sheet in sheets]
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:limit]

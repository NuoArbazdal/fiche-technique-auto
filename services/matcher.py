from rapidfuzz import fuzz

from .text_utils import normalize_text


def _clean(value: str) -> str:
    return normalize_text(value or "")


def score_query(query: str, sheet: dict) -> int:
    q = _clean(query)
    if not q:
        return 0

    names = [sheet.get("product_name", "")]
    names.extend(sheet.get("aliases", []) or [])

    name_scores = []
    for candidate in names:
        c = _clean(candidate)
        if not c:
            continue

        scores = [
            fuzz.token_set_ratio(q, c),
            fuzz.token_sort_ratio(q, c),
            fuzz.WRatio(q, c),
        ]

        if q == c:
            scores.append(100)
        elif q in c or c in q:
            scores.append(96)

        name_scores.append(max(scores))

    best = max(name_scores) if name_scores else 0

    reference = _clean(sheet.get("reference", ""))
    if reference and reference in q:
        best = max(best, 99)

    brand = _clean(sheet.get("brand", ""))
    if brand and brand in q and best >= 75:
        best = min(100, best + 3)

    return int(round(best))


def search_library(query: str, sheets: list[dict], limit: int = 5):
    ranked = [(score_query(query, sheet), sheet) for sheet in sheets]
    ranked.sort(
        key=lambda item: (
            item[0],
            len(item[1].get("product_name", "") or ""),
        ),
        reverse=True,
    )
    return ranked[:limit]

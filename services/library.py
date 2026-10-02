from pathlib import Path
from .db import get_supabase
from .text_utils import normalize_text

BUCKET = "technical-sheets"

def list_sheets():
    supabase = get_supabase()
    result = (
        supabase.table("technical_sheets")
        .select("*, technical_sheet_aliases(alias, normalized_alias)")
        .eq("active", True)
        .order("product_name")
        .execute()
    )
    rows = result.data or []
    for row in rows:
        row["aliases"] = [
            a.get("alias", "")
            for a in (row.get("technical_sheet_aliases") or [])
        ]
    return rows

def save_sheet(metadata: dict, filename: str, pdf_bytes: bytes):
    supabase = get_supabase()

    brand_slug = normalize_text(metadata.get("brand") or "sans-marque").replace(" ", "-")
    safe_name = Path(filename).name
    path = f"{brand_slug}/{safe_name}"

    supabase.storage.from_(BUCKET).upload(
        path=path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )

    row = (
        supabase.table("technical_sheets")
        .insert({
            "product_name": metadata["product_name"].strip(),
            "brand": metadata.get("brand") or None,
            "category": metadata.get("category") or None,
            "reference": metadata.get("reference") or None,
            "storage_path": path,
            "original_filename": safe_name,
            "version_label": metadata.get("version_label") or None,
        })
        .execute()
    ).data[0]

    aliases = [metadata["product_name"]] + list(metadata.get("aliases") or [])
    alias_rows = []
    seen = set()
    for alias in aliases:
        normalized = normalize_text(alias)
        if normalized and normalized not in seen:
            seen.add(normalized)
            alias_rows.append({
                "technical_sheet_id": row["id"],
                "alias": alias,
                "normalized_alias": normalized,
            })

    if alias_rows:
        supabase.table("technical_sheet_aliases").insert(alias_rows).execute()

    return row

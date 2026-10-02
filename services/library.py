from pathlib import Path
from uuid import uuid4

from .db import get_supabase
from .text_utils import normalize_text

BUCKET = "technical-sheets"


def _alias_rows(sheet_id: str, product_name: str, aliases: list[str]):
    values = [product_name] + list(aliases or [])
    rows = []
    seen = set()

    for alias in values:
        normalized = normalize_text(alias)
        if normalized and normalized not in seen:
            seen.add(normalized)
            rows.append({
                "technical_sheet_id": sheet_id,
                "alias": alias,
                "normalized_alias": normalized,
            })

    return rows


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

    alias_rows = _alias_rows(
        row["id"],
        metadata["product_name"],
        metadata.get("aliases") or [],
    )

    if alias_rows:
        supabase.table("technical_sheet_aliases").insert(alias_rows).execute()

    return row


def get_sheet(sheet_id: str):
    supabase = get_supabase()
    result = (
        supabase.table("technical_sheets")
        .select("*, technical_sheet_aliases(alias, normalized_alias)")
        .eq("id", sheet_id)
        .single()
        .execute()
    )

    row = result.data
    if row:
        row["aliases"] = [
            a.get("alias", "")
            for a in (row.get("technical_sheet_aliases") or [])
        ]

    return row


def download_sheet_pdf(sheet_id: str) -> bytes:
    sheet = get_sheet(sheet_id)
    if not sheet:
        raise ValueError("Fiche technique introuvable dans la bibliothèque.")

    storage_path = sheet.get("storage_path")
    if not storage_path:
        raise ValueError("Le chemin du PDF de la fiche est manquant.")

    supabase = get_supabase()
    return supabase.storage.from_(BUCKET).download(storage_path)


def update_sheet_metadata(sheet_id: str, metadata: dict):
    supabase = get_supabase()

    payload = {
        "product_name": metadata["product_name"].strip(),
        "brand": metadata.get("brand") or None,
        "category": metadata.get("category") or None,
        "reference": metadata.get("reference") or None,
        "version_label": metadata.get("version_label") or None,
    }

    (
        supabase.table("technical_sheets")
        .update(payload)
        .eq("id", sheet_id)
        .execute()
    )

    (
        supabase.table("technical_sheet_aliases")
        .delete()
        .eq("technical_sheet_id", sheet_id)
        .execute()
    )

    alias_rows = _alias_rows(
        sheet_id,
        metadata["product_name"],
        metadata.get("aliases") or [],
    )

    if alias_rows:
        supabase.table("technical_sheet_aliases").insert(alias_rows).execute()

    return get_sheet(sheet_id)


def replace_sheet_pdf(sheet_id: str, filename: str, pdf_bytes: bytes):
    supabase = get_supabase()
    sheet = get_sheet(sheet_id)

    if not sheet:
        raise ValueError("Fiche technique introuvable.")

    old_path = sheet.get("storage_path")
    brand_slug = normalize_text(sheet.get("brand") or "sans-marque").replace(" ", "-")
    safe_name = Path(filename).name
    new_path = f"{brand_slug}/{sheet_id}/{uuid4().hex}-{safe_name}"

    supabase.storage.from_(BUCKET).upload(
        path=new_path,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )

    (
        supabase.table("technical_sheets")
        .update({
            "storage_path": new_path,
            "original_filename": safe_name,
        })
        .eq("id", sheet_id)
        .execute()
    )

    if old_path and old_path != new_path:
        try:
            supabase.storage.from_(BUCKET).remove([old_path])
        except Exception:
            pass

    return get_sheet(sheet_id)


def delete_sheet(sheet_id: str):
    supabase = get_supabase()
    sheet = get_sheet(sheet_id)

    if not sheet:
        return

    storage_path = sheet.get("storage_path")

    (
        supabase.table("technical_sheets")
        .delete()
        .eq("id", sheet_id)
        .execute()
    )

    if storage_path:
        try:
            supabase.storage.from_(BUCKET).remove([storage_path])
        except Exception:
            pass

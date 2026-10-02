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


def find_duplicate(metadata: dict, filename: str, sheets: list[dict] | None = None):
    """Retourne (niveau, fiche, raison) ou (None, None, None).

    exact = doublon suffisamment sûr pour être ignoré automatiquement.
    probable = nom très proche : on signale mais on n'écrase rien.
    """
    from rapidfuzz import fuzz

    sheets = sheets if sheets is not None else list_sheets()
    new_name = normalize_text(metadata.get("product_name") or "")
    new_brand = normalize_text(metadata.get("brand") or "")
    new_ref = normalize_text(metadata.get("reference") or "")
    new_version = normalize_text(metadata.get("version_label") or "")
    new_filename = normalize_text(Path(filename).name)

    for sheet in sheets:
        old_filename = normalize_text(sheet.get("original_filename") or "")
        old_name = normalize_text(sheet.get("product_name") or "")
        old_brand = normalize_text(sheet.get("brand") or "")
        old_ref = normalize_text(sheet.get("reference") or "")
        old_version = normalize_text(sheet.get("version_label") or "")

        if new_filename and old_filename and new_filename == old_filename:
            return "exact", sheet, "même nom de fichier"

        if new_ref and old_ref and new_ref == old_ref:
            if not new_brand or not old_brand or new_brand == old_brand:
                if not (new_version and old_version and new_version != old_version):
                    return "exact", sheet, "même référence produit"

        if new_name and old_name and new_name == old_name:
            if not new_brand or not old_brand or new_brand == old_brand:
                if not (new_version and old_version and new_version != old_version):
                    return "exact", sheet, "même produit"

    best = None
    best_score = 0

    for sheet in sheets:
        old_name = normalize_text(sheet.get("product_name") or "")
        if not new_name or not old_name:
            continue

        old_brand = normalize_text(sheet.get("brand") or "")
        if new_brand and old_brand and new_brand != old_brand:
            continue

        score = max(
            fuzz.token_set_ratio(new_name, old_name),
            fuzz.WRatio(new_name, old_name),
        )

        if score > best_score:
            best_score = score
            best = sheet

    if best is not None and best_score >= 96:
        return "probable", best, f"nom très proche ({int(best_score)} %)"

    return None, None, None

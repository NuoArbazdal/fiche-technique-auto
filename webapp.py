from io import BytesIO

from flask import Flask, jsonify, render_template, request, send_file

from services.library import (
    delete_sheet,
    download_sheet_pdf,
    find_duplicate,
    list_sheets,
    replace_sheet_pdf,
    save_sheet,
    update_sheet_metadata,
)
from services.matcher import search_library
from services.metadata import detect_metadata
from services.pdf_builder import build_dossier_pdf


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024

APP_VERSION = "2026-10-05-word-size-reference-v3"


@app.after_request
def disable_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/")
def index():
    return render_template("index.html", app_version=APP_VERSION)


@app.get("/api/library")
def api_library():
    return jsonify(list_sheets())


@app.post("/api/library/import-one")
def api_import_one():
    pdf = request.files.get("file")
    if not pdf:
        return jsonify({"error": "Aucun PDF reçu."}), 400

    pdf_bytes = pdf.read()
    metadata = detect_metadata(pdf.filename, pdf_bytes)
    level, duplicate, reason = find_duplicate(metadata, pdf.filename, list_sheets())

    if level == "exact":
        return jsonify({
            "status": "duplicate",
            "metadata": metadata,
            "duplicate": duplicate,
            "reason": reason,
        })

    saved = save_sheet(metadata, pdf.filename, pdf_bytes)
    return jsonify({
        "status": "imported",
        "sheet": saved,
        "metadata": metadata,
        "possible_duplicate": duplicate if level == "probable" else None,
        "reason": reason if level == "probable" else None,
    })


@app.post("/api/library/<sheet_id>/metadata")
def api_update_metadata(sheet_id):
    payload = request.get_json(force=True) or {}
    if not (payload.get("product_name") or "").strip():
        return jsonify({"error": "Le nom du produit est obligatoire."}), 400
    return jsonify(update_sheet_metadata(sheet_id, payload))


@app.post("/api/library/<sheet_id>/replace")
def api_replace_pdf(sheet_id):
    pdf = request.files.get("file")
    if not pdf:
        return jsonify({"error": "Aucun PDF reçu."}), 400
    return jsonify(replace_sheet_pdf(sheet_id, pdf.filename, pdf.read()))


@app.delete("/api/library/<sheet_id>")
def api_delete_sheet(sheet_id):
    delete_sheet(sheet_id)
    return jsonify({"ok": True})


@app.get("/api/library/<sheet_id>/pdf")
def api_sheet_pdf(sheet_id):
    pdf_bytes = download_sheet_pdf(sheet_id)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name="fiche-technique.pdf",
    )


@app.post("/api/match")
def api_match():
    payload = request.get_json(force=True) or {}
    rows = payload.get("rows") or []
    sheets = list_sheets()
    results = []

    for idx, row in enumerate(rows):
        item = {
            "id": row.get("id"),
            "order": idx + 1,
            "type": row.get("type"),
            "designation": (row.get("designation") or "").strip(),
            "candidates": [],
        }

        if row.get("type") == "FT" and item["designation"]:
            matches = search_library(item["designation"], sheets, limit=5)
            item["candidates"] = [
                {
                    "id": sheet.get("id"),
                    "product_name": sheet.get("product_name", ""),
                    "brand": sheet.get("brand") or "",
                    "score": int(score),
                }
                for score, sheet in matches
            ]

        results.append(item)

    return jsonify(results)


@app.post("/api/generate")
def api_generate():
    payload = request.get_json(force=True) or {}
    items = payload.get("items") or []
    if not items:
        return jsonify({"error": "Le dossier est vide."}), 400

    pdf_bytes = build_dossier_pdf([
        {
            "Type": item.get("type"),
            "Désignation": item.get("designation") or "",
            "font_size": item.get("font_size"),
            "technical_sheet_id": item.get("technical_sheet_id"),
        }
        for item in items
    ])

    filename = (payload.get("filename") or "dossier_fiches_techniques.pdf").strip()
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

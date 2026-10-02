import pandas as pd
import streamlit as st

from services.metadata import detect_metadata
from services.library import list_sheets, save_sheet
from services.matcher import search_library
from services.pdf_builder import build_dossier_pdf

st.set_page_config(page_title="Fiches techniques", page_icon="📄", layout="centered")

st.title("Fiches techniques")
st.caption("Créer un dossier à partir de fiches fabricants originales, sans les modifier.")


def normalize_plan(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "Type" not in work.columns:
        work["Type"] = "Titre principal"
    if "Désignation" not in work.columns:
        work["Désignation"] = ""

    work["Type"] = work["Type"].fillna("Titre principal").astype(str)
    work["Type"] = work["Type"].replace({"Titre": "Titre principal"})
    work["Désignation"] = work["Désignation"].fillna("").astype(str)
    return work[["Type", "Désignation"]].reset_index(drop=True)


def clear_results():
    st.session_state.pop("manual_results", None)
    st.session_state.pop("generated_pdf", None)


def set_plan_and_rerun(df: pd.DataFrame):
    st.session_state.manual_plan = normalize_plan(df)
    clear_results()
    st.rerun()


def move_row(df: pd.DataFrame, index: int, direction: int):
    work = normalize_plan(df)
    target = index + direction
    if 0 <= target < len(work):
        rows = work.to_dict("records")
        rows[index], rows[target] = rows[target], rows[index]
        set_plan_and_rerun(pd.DataFrame(rows))


def duplicate_row(df: pd.DataFrame, index: int):
    work = normalize_plan(df)
    rows = work.to_dict("records")
    rows.insert(index + 1, dict(rows[index]))
    set_plan_and_rerun(pd.DataFrame(rows))


def delete_row(df: pd.DataFrame, index: int):
    work = normalize_plan(df)
    work = work.drop(index=index).reset_index(drop=True)
    if work.empty:
        work = pd.DataFrame([{"Type": "Titre principal", "Désignation": ""}])
    set_plan_and_rerun(work)


tab_build, tab_library = st.tabs(["Créer un dossier", "Bibliothèque"])

with tab_build:
    st.subheader("1. Saisir le contenu du dossier")
    st.write(
        "Ajoute les titres et les fiches techniques dans l'ordre souhaité. "
        "La page d'accueil du dossier sera ajoutée plus tard."
    )

    if "manual_plan" not in st.session_state:
        st.session_state.manual_plan = pd.DataFrame(
            [
                {"Type": "Titre principal", "Désignation": ""},
                {"Type": "Sous-titre", "Désignation": ""},
                {"Type": "FT", "Désignation": ""},
            ]
        )

    plan = st.data_editor(
        normalize_plan(st.session_state.manual_plan),
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Type": st.column_config.SelectboxColumn(
                "Type",
                options=["Titre principal", "Sous-titre", "FT"],
                required=True,
                width="medium",
            ),
            "Désignation": st.column_config.TextColumn(
                "Titre ou nom de la fiche technique",
                required=True,
                width="large",
            ),
        },
        key="manual_plan_editor",
    )

    st.caption(
        "Titre principal = grand titre en majuscules. "
        "Sous-titre = titre intermédiaire plus petit. "
        "FT = PDF fabricant original."
    )

    current_plan = normalize_plan(plan)

    if len(current_plan):
        with st.expander("Réorganiser les lignes"):
            for idx, row in current_plan.iterrows():
                c_text, c_up, c_down, c_dup, c_del = st.columns([5, 1, 1, 1, 1])
                with c_text:
                    label = row["Désignation"].strip() or "(ligne vide)"
                    st.write(f"**{idx + 1}. {row['Type']}** — {label}")
                with c_up:
                    if st.button("↑", key=f"up-{idx}", disabled=idx == 0):
                        move_row(current_plan, idx, -1)
                with c_down:
                    if st.button("↓", key=f"down-{idx}", disabled=idx == len(current_plan) - 1):
                        move_row(current_plan, idx, 1)
                with c_dup:
                    if st.button("⧉", key=f"dup-{idx}", help="Dupliquer"):
                        duplicate_row(current_plan, idx)
                with c_del:
                    if st.button("✕", key=f"del-{idx}", help="Supprimer"):
                        delete_row(current_plan, idx)

    if st.button("Rechercher les fiches techniques", type="primary"):
        clean_plan = normalize_plan(current_plan)
        clean_plan["Désignation"] = clean_plan["Désignation"].str.strip()
        clean_plan = clean_plan[clean_plan["Désignation"] != ""].reset_index(drop=True)

        if clean_plan.empty:
            st.warning("Ajoute au moins un titre ou une fiche technique.")
        else:
            sheets = list_sheets()
            results = []

            for idx, row in clean_plan.iterrows():
                item = {
                    "Ordre": idx + 1,
                    "Type": row["Type"],
                    "Désignation": row["Désignation"],
                    "Fiche proposée": "",
                    "Marque": "",
                    "Score": None,
                    "Statut": "",
                    "technical_sheet_id": None,
                    "candidates": [],
                }

                if row["Type"] == "FT":
                    matches = search_library(row["Désignation"], sheets, limit=5) if sheets else []
                    item["candidates"] = [
                        {
                            "id": sheet.get("id"),
                            "product_name": sheet.get("product_name", ""),
                            "brand": sheet.get("brand", "") or "",
                            "score": int(score),
                        }
                        for score, sheet in matches
                    ]

                    if matches:
                        score, sheet = matches[0]
                        item["Fiche proposée"] = sheet.get("product_name", "")
                        item["Marque"] = sheet.get("brand", "") or ""
                        item["Score"] = int(score)
                        item["technical_sheet_id"] = sheet.get("id")

                        if score >= 90:
                            item["Statut"] = "Trouvée"
                        elif score >= 70:
                            item["Statut"] = "À confirmer"
                        else:
                            item["Statut"] = "Correspondance trop faible"
                    else:
                        item["Statut"] = "Introuvable"
                else:
                    item["Statut"] = "Page de titre"

                results.append(item)

            st.session_state["manual_results"] = results
            st.session_state["manual_plan"] = clean_plan[["Type", "Désignation"]]
            st.session_state.pop("generated_pdf", None)

    if "manual_results" in st.session_state:
        st.subheader("2. Vérifier les correspondances")
        results = st.session_state["manual_results"]

        for i, row in enumerate(results):
            if row["Type"] in ("Titre principal", "Sous-titre"):
                st.write(f"**{row['Ordre']}. {row['Type'].upper()}** — {row['Désignation']}")
                continue

            st.markdown(f"**{row['Ordre']}. FT — {row['Désignation']}**")

            candidates = row.get("candidates", [])
            if candidates:
                options = [c["id"] for c in candidates]
                labels = {
                    c["id"]: (
                        f"{c['product_name']}"
                        + (f" — {c['brand']}" if c["brand"] else "")
                        + f" — {c['score']} %"
                    )
                    for c in candidates
                }

                selected_id = st.selectbox(
                    "Fiche à utiliser",
                    options=options,
                    index=options.index(row["technical_sheet_id"]) if row["technical_sheet_id"] in options else 0,
                    format_func=lambda x: labels.get(x, x),
                    key=f"candidate-{i}",
                )

                selected = next(c for c in candidates if c["id"] == selected_id)
                row["technical_sheet_id"] = selected["id"]
                row["Fiche proposée"] = selected["product_name"]
                row["Marque"] = selected["brand"]
                row["Score"] = selected["score"]

                if selected["score"] >= 90:
                    row["Statut"] = "Trouvée"
                else:
                    row["Statut"] = "Choisie manuellement"

                st.caption(f"Statut : {row['Statut']}")
            else:
                st.warning("Aucune fiche correspondante trouvée dans la bibliothèque.")

                missing_pdf = st.file_uploader(
                    "Ajouter directement la fiche PDF manquante",
                    type=["pdf"],
                    key=f"missing-pdf-{i}",
                )

                if missing_pdf:
                    metadata = detect_metadata(missing_pdf.name, missing_pdf.getvalue())
                    metadata["product_name"] = row["Désignation"]

                    st.write(
                        f"Produit : **{metadata['product_name']}**"
                        + (f" — Marque détectée : **{metadata['brand']}**" if metadata.get("brand") else "")
                    )

                    if st.button("Ajouter à la bibliothèque", key=f"save-missing-{i}"):
                        try:
                            save_sheet(metadata, missing_pdf.name, missing_pdf.getvalue())
                            st.success("Fiche ajoutée. Relance la recherche pour l'associer au dossier.")
                        except Exception as exc:
                            st.error(f"Impossible d'ajouter la fiche : {exc}")

            st.divider()

        ft_rows = [row for row in results if row["Type"] == "FT"]
        unresolved = [
            row for row in ft_rows
            if not row.get("technical_sheet_id")
        ]

        if unresolved:
            st.warning(
                f"{len(unresolved)} fiche(s) doivent encore être ajoutées ou sélectionnées."
            )
        else:
            st.success(
                "Toutes les fiches techniques sont associées. "
                "Le dossier peut être généré."
            )

            st.subheader("3. Générer le dossier PDF")
            st.caption(
                "Les pages de titre reprennent le principe de tes modèles : "
                "page blanche, texte bleu centré et souligné. "
                "La page d'accueil complète n'est pas encore incluse."
            )

            if st.button("Générer le PDF final", type="primary"):
                try:
                    with st.spinner("Création du dossier..."):
                        st.session_state["generated_pdf"] = build_dossier_pdf(results)
                    st.success("PDF généré.")
                except Exception as exc:
                    st.error(f"Impossible de générer le PDF : {exc}")

            if st.session_state.get("generated_pdf"):
                st.download_button(
                    "Télécharger le dossier PDF",
                    data=st.session_state["generated_pdf"],
                    file_name="dossier_fiches_techniques.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

with tab_library:
    st.subheader("Importer un dossier de fiches techniques")
    st.write(
        "Sélectionne directement le dossier complet sur ton PC. "
        "Le site récupère automatiquement tous les PDF du dossier et de ses sous-dossiers."
    )

    uploads = st.file_uploader(
        "Choisir le dossier contenant les fiches techniques",
        type=["pdf"],
        accept_multiple_files="directory",
        key="library_uploads",
        help="Le navigateur enverra tous les PDF présents dans le dossier sélectionné et ses sous-dossiers.",
    )

    if uploads:
        total_size = sum(pdf.size for pdf in uploads)
        top_folders = sorted({
            pdf.name.split("/")[0]
            for pdf in uploads
            if "/" in pdf.name
        })
        folder_label = ", ".join(top_folders[:3]) if top_folders else "dossier sélectionné"

        st.caption(
            f"{len(uploads)} PDF trouvés dans {folder_label} — "
            f"{total_size / (1024 * 1024):.1f} Mo au total"
        )

        if st.button(
            f"Importer tout le dossier ({len(uploads)} PDF)",
            type="primary",
            use_container_width=True,
        ):
            progress = st.progress(0)
            status = st.empty()
            imported = []
            skipped = []
            failed = []

            for index, pdf in enumerate(uploads, start=1):
                status.write(f"Import de **{pdf.name}** ({index}/{len(uploads)})...")

                try:
                    metadata = detect_metadata(pdf.name, pdf.getvalue())
                    save_sheet(metadata, pdf.name, pdf.getvalue())
                    imported.append({
                        "Fichier": pdf.name,
                        "Produit détecté": metadata.get("product_name", ""),
                        "Marque": metadata.get("brand", ""),
                    })
                except Exception as exc:
                    message = str(exc)
                    lower = message.lower()

                    if (
                        "duplicate" in lower
                        or "already exists" in lower
                        or "resource already exists" in lower
                        or "409" in lower
                    ):
                        skipped.append(pdf.name)
                    else:
                        failed.append((pdf.name, message))

                progress.progress(index / len(uploads))

            status.empty()
            progress.empty()

            if imported:
                st.success(
                    f"{len(imported)} fiche(s) ajoutée(s) automatiquement à la bibliothèque."
                )
                st.dataframe(
                    pd.DataFrame(imported),
                    hide_index=True,
                    use_container_width=True,
                )

            if skipped:
                st.info(
                    f"{len(skipped)} fichier(s) déjà présent(s) ont été ignoré(s)."
                )
                with st.expander("Voir les fichiers ignorés"):
                    for name in skipped:
                        st.write(name)

            if failed:
                st.warning(
                    f"{len(failed)} fichier(s) n'ont pas pu être importé(s). "
                    "Les autres fiches ont quand même été ajoutées."
                )
                with st.expander("Voir les erreurs"):
                    for name, message in failed:
                        st.write(f"**{name}** — {message}")

            st.session_state.pop("manual_results", None)

    st.divider()
    st.subheader("Bibliothèque existante")
    try:
        sheets = list_sheets()
        st.caption(f"{len(sheets)} fiche(s) actuellement enregistrée(s).")
        if not sheets:
            st.caption("Bibliothèque vide.")
        for sheet in sheets:
            st.write(
                f"**{sheet['product_name']}**"
                + (f" — {sheet.get('brand')}" if sheet.get("brand") else "")
                + f" — {sheet['original_filename']}"
            )
    except Exception as exc:
        st.caption(f"Bibliothèque indisponible : {exc}")

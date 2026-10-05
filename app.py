from uuid import uuid4

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, JsCode

from services.metadata import detect_metadata
from services.library import (
    list_sheets,
    save_sheet,
    download_sheet_pdf,
    update_sheet_metadata,
    replace_sheet_pdf,
    delete_sheet,
    find_duplicate,
)
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


def ensure_plan_ids(df: pd.DataFrame) -> pd.DataFrame:
    work = normalize_plan(df)
    source = df.copy()

    if "_id" in source.columns and len(source) == len(work):
        ids = source["_id"].fillna("").astype(str).tolist()
    else:
        ids = [""] * len(work)

    work["_id"] = [
        value if value else uuid4().hex
        for value in ids
    ]
    return work[["_id", "Type", "Désignation"]].reset_index(drop=True)


def clear_results():
    st.session_state.pop("manual_results", None)
    st.session_state.pop("generated_pdf", None)


def set_plan_and_rerun(df: pd.DataFrame):
    st.session_state.manual_plan = ensure_plan_ids(df)
    st.session_state["manual_grid_version"] = st.session_state.get("manual_grid_version", 0) + 1
    clear_results()
    st.rerun()


def add_row(df: pd.DataFrame, row_type: str):
    work = ensure_plan_ids(df)
    rows = work.to_dict("records")
    rows.append({"_id": uuid4().hex, "Type": row_type, "Désignation": ""})
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
        st.session_state.manual_plan = ensure_plan_ids(
            pd.DataFrame(
                [
                    {"Type": "Titre principal", "Désignation": ""},
                    {"Type": "Sous-titre", "Désignation": ""},
                    {"Type": "FT", "Désignation": ""},
                ]
            )
        )

    editor_df = ensure_plan_ids(st.session_state.manual_plan).copy()
    editor_df["_order"] = list(range(len(editor_df)))
    editor_df["Supprimer"] = "🗑️"

    gb = GridOptionsBuilder.from_dataframe(editor_df)
    gb.configure_column("_id", hide=True, editable=False)
    gb.configure_column(
        "Type",
        header_name="Type",
        editable=True,
        rowDrag=True,
        width=220,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": ["Titre principal", "Sous-titre", "FT"]},
    )
    gb.configure_column(
        "Désignation",
        header_name="Titre ou nom de la fiche technique",
        editable=True,
        flex=1,
        minWidth=360,
    )

    trash_renderer = JsCode("""
        function(params) {
            return '🗑️';
        }
    """)

    delete_click = JsCode("""
        function(params) {
            if (params.colDef.field === 'Supprimer') {
                params.node.setSelected(true, true);
            }
        }
    """)

    row_drag_end = JsCode("""
        function(params) {
            let i = 0;
            params.api.forEachNode(function(node) {
                node.setDataValue('_order', i);
                i += 1;
            });
        }
    """)

    get_row_id = JsCode("""
        function(params) {
            return params.data._id;
        }
    """)

    gb.configure_column(
        "Supprimer",
        header_name="",
        editable=False,
        width=64,
        cellRenderer=trash_renderer,
        suppressMenu=True,
        sortable=False,
        filter=False,
        resizable=False,
        pinned="right",
        cellStyle={"cursor": "pointer", "textAlign": "center", "fontSize": "18px"},
    )
    gb.configure_column("_order", hide=True, editable=False)

    gb.configure_grid_options(
        rowDragManaged=True,
        rowDragEntireRow=True,
        animateRows=True,
        suppressMoveWhenRowDragging=False,
        stopEditingWhenCellsLoseFocus=True,
        rowSelection="single",
        suppressRowClickSelection=True,
        onCellClicked=delete_click,
        onRowDragEnd=row_drag_end,
        getRowId=get_row_id,
    )

    if "manual_grid_version" not in st.session_state:
        st.session_state.manual_grid_version = 0

    grid_response = AgGrid(
        editor_df,
        gridOptions=gb.build(),
        height=max(150, min(520, 42 * (len(editor_df) + 1))),
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_on=["cellValueChanged", "rowDragEnd", "selectionChanged"],
        key=f"manual_plan_grid_{st.session_state.manual_grid_version}",
        theme="streamlit",
    )

    grid_data = pd.DataFrame(grid_response["data"])
    if "_order" not in grid_data.columns:
        grid_data["_order"] = list(range(len(grid_data)))
    if "_id" not in grid_data.columns:
        grid_data = ensure_plan_ids(grid_data)
        grid_data["_order"] = list(range(len(grid_data)))

    selected_rows = grid_response.get("selected_rows")
    if selected_rows is not None:
        selected_df = pd.DataFrame(selected_rows)
        if not selected_df.empty and "_id" in selected_df.columns:
            selected_id = str(selected_df.iloc[0]["_id"])
            cleaned = (
                grid_data.loc[grid_data["_id"].astype(str) != selected_id]
                .sort_values("_order")
                [["_id", "Type", "Désignation"]]
                .reset_index(drop=True)
            )
            if cleaned.empty:
                cleaned = ensure_plan_ids(
                    pd.DataFrame([{"Type": "Titre principal", "Désignation": ""}])
                )
            set_plan_and_rerun(cleaned)

    current_state = (
        grid_data.sort_values("_order")
        [["_id", "Type", "Désignation"]]
        .reset_index(drop=True)
    )
    current_plan = normalize_plan(current_state)

    stored_state = ensure_plan_ids(st.session_state.manual_plan)
    if not current_state.equals(stored_state):
        st.session_state.manual_plan = current_state.copy()
        clear_results()

    st.caption(
        "Maintiens le clic sur une ligne puis fais-la glisser pour changer l'ordre. "
        "La corbeille à droite supprime immédiatement la ligne."
    )

    st.markdown("**Ajouter rapidement une ligne**")
    add_main, add_sub, add_ft = st.columns(3)
    with add_main:
        if st.button("+ Titre principal", use_container_width=True):
            add_row(current_plan, "Titre principal")
    with add_sub:
        if st.button("+ Sous-titre", use_container_width=True):
            add_row(current_plan, "Sous-titre")
    with add_ft:
        if st.button("+ FT", use_container_width=True):
            add_row(current_plan, "FT")

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
            possible_duplicates = []
            failed = []
            existing_sheets = list_sheets()

            for index, pdf in enumerate(uploads, start=1):
                status.write(f"Import de **{pdf.name}** ({index}/{len(uploads)})...")

                try:
                    metadata = detect_metadata(pdf.name, pdf.getvalue())
                    duplicate_level, duplicate_sheet, duplicate_reason = find_duplicate(
                        metadata,
                        pdf.name,
                        existing_sheets,
                    )

                    if duplicate_level == "exact":
                        skipped.append(
                            {
                                "Fichier": pdf.name,
                                "Doublon de": duplicate_sheet.get("product_name", ""),
                                "Raison": duplicate_reason,
                            }
                        )
                    else:
                        saved = save_sheet(metadata, pdf.name, pdf.getvalue())
                        imported.append({
                            "Fichier": pdf.name,
                            "Produit détecté": metadata.get("product_name", ""),
                            "Marque": metadata.get("brand", ""),
                        })
                        existing_sheets.append({
                            **saved,
                            "aliases": metadata.get("aliases") or [],
                        })

                        if duplicate_level == "probable":
                            possible_duplicates.append({
                                "Fichier importé": pdf.name,
                                "Proche de": duplicate_sheet.get("product_name", ""),
                                "Raison": duplicate_reason,
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
                    f"{len(skipped)} doublon(s) certain(s) ont été ignoré(s) automatiquement."
                )
                st.dataframe(
                    pd.DataFrame(skipped),
                    hide_index=True,
                    use_container_width=True,
                )

            if possible_duplicates:
                st.warning(
                    f"{len(possible_duplicates)} fiche(s) importée(s) ressemblent fortement "
                    "à une fiche déjà présente. Elles n'ont pas été supprimées automatiquement."
                )
                st.dataframe(
                    pd.DataFrame(possible_duplicates),
                    hide_index=True,
                    use_container_width=True,
                )

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
    st.subheader("Gérer la bibliothèque")

    try:
        sheets = list_sheets()
    except Exception as exc:
        sheets = []
        st.error(f"Bibliothèque indisponible : {exc}")

    if sheets:
        st.caption(f"{len(sheets)} fiche(s) actuellement enregistrée(s).")

        search = st.text_input(
            "Rechercher une fiche",
            placeholder="Nom du produit, marque, référence...",
            key="library_search",
        )

        brands = sorted({
            (sheet.get("brand") or "").strip()
            for sheet in sheets
            if (sheet.get("brand") or "").strip()
        })
        categories = sorted({
            (sheet.get("category") or "").strip()
            for sheet in sheets
            if (sheet.get("category") or "").strip()
        })

        c_brand, c_category = st.columns(2)
        with c_brand:
            brand_filter = st.selectbox(
                "Marque",
                ["Toutes"] + brands,
                key="library_brand_filter",
            )
        with c_category:
            category_filter = st.selectbox(
                "Catégorie",
                ["Toutes"] + categories,
                key="library_category_filter",
            )

        filtered = []
        needle = search.strip().lower()

        for sheet in sheets:
            haystack = " ".join([
                sheet.get("product_name", "") or "",
                sheet.get("brand", "") or "",
                sheet.get("reference", "") or "",
                sheet.get("category", "") or "",
                sheet.get("original_filename", "") or "",
                " ".join(sheet.get("aliases") or []),
            ]).lower()

            if needle and needle not in haystack:
                continue
            if brand_filter != "Toutes" and sheet.get("brand") != brand_filter:
                continue
            if category_filter != "Toutes" and sheet.get("category") != category_filter:
                continue

            filtered.append(sheet)

        st.caption(f"{len(filtered)} fiche(s) affichée(s).")

        for sheet in filtered:
            sheet_id = sheet["id"]
            title = sheet.get("product_name") or sheet.get("original_filename") or "Fiche technique"
            brand = sheet.get("brand") or "Sans marque"

            with st.expander(f"{title} — {brand}"):
                st.caption(
                    f"Fichier : {sheet.get('original_filename', '')}"
                    + (
                        f" — Référence : {sheet.get('reference')}"
                        if sheet.get("reference")
                        else ""
                    )
                )

                c_preview, c_download = st.columns(2)

                with c_preview:
                    if st.button("Afficher la fiche", key=f"preview-{sheet_id}"):
                        st.session_state["preview_sheet_id"] = sheet_id

                with c_download:
                    try:
                        pdf_bytes = download_sheet_pdf(sheet_id)
                        st.download_button(
                            "Télécharger le PDF original",
                            data=pdf_bytes,
                            file_name=sheet.get("original_filename") or "fiche.pdf",
                            mime="application/pdf",
                            key=f"download-{sheet_id}",
                            use_container_width=True,
                        )
                    except Exception as exc:
                        st.error(f"PDF indisponible : {exc}")

                if st.session_state.get("preview_sheet_id") == sheet_id:
                    try:
                        pdf_bytes = download_sheet_pdf(sheet_id)
                        st.markdown("**Aperçu**")
                        if hasattr(st, "pdf"):
                            st.pdf(pdf_bytes, height=700)
                        else:
                            st.info(
                                "L'aperçu PDF intégré n'est pas disponible sur cette version. "
                                "Utilise le bouton de téléchargement ci-dessus."
                            )
                    except Exception as exc:
                        st.error(f"Aperçu impossible : {exc}")

                st.markdown("**Modifier les informations**")
                edit_product = st.text_input(
                    "Nom du produit",
                    value=sheet.get("product_name") or "",
                    key=f"edit-product-{sheet_id}",
                )
                e1, e2 = st.columns(2)
                with e1:
                    edit_brand = st.text_input(
                        "Marque",
                        value=sheet.get("brand") or "",
                        key=f"edit-brand-{sheet_id}",
                    )
                    edit_reference = st.text_input(
                        "Référence",
                        value=sheet.get("reference") or "",
                        key=f"edit-reference-{sheet_id}",
                    )
                with e2:
                    edit_category = st.text_input(
                        "Catégorie",
                        value=sheet.get("category") or "",
                        key=f"edit-category-{sheet_id}",
                    )
                    edit_version = st.text_input(
                        "Version / date",
                        value=sheet.get("version_label") or "",
                        key=f"edit-version-{sheet_id}",
                    )

                edit_aliases = st.text_input(
                    "Alias",
                    value=", ".join(sheet.get("aliases") or []),
                    key=f"edit-aliases-{sheet_id}",
                )

                if st.button("Enregistrer les modifications", key=f"save-edit-{sheet_id}"):
                    try:
                        update_sheet_metadata(
                            sheet_id,
                            {
                                "product_name": edit_product,
                                "brand": edit_brand,
                                "reference": edit_reference,
                                "category": edit_category,
                                "version_label": edit_version,
                                "aliases": [
                                    a.strip()
                                    for a in edit_aliases.split(",")
                                    if a.strip()
                                ],
                            },
                        )
                        st.success("Fiche modifiée.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Modification impossible : {exc}")

                st.markdown("**Remplacer le PDF**")
                replacement = st.file_uploader(
                    "Choisir le nouveau PDF",
                    type=["pdf"],
                    key=f"replace-upload-{sheet_id}",
                )

                if replacement is not None:
                    if st.button("Remplacer cette fiche", key=f"replace-{sheet_id}"):
                        try:
                            replace_sheet_pdf(
                                sheet_id,
                                replacement.name,
                                replacement.getvalue(),
                            )
                            st.success("PDF remplacé. L'ancien fichier a été retiré du stockage.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Remplacement impossible : {exc}")

                st.markdown("**Supprimer la fiche**")
                confirm_delete = st.checkbox(
                    "Je confirme la suppression de cette fiche",
                    key=f"confirm-delete-{sheet_id}",
                )
                if st.button(
                    "Supprimer définitivement",
                    key=f"delete-{sheet_id}",
                    disabled=not confirm_delete,
                ):
                    try:
                        delete_sheet(sheet_id)
                        if st.session_state.get("preview_sheet_id") == sheet_id:
                            st.session_state.pop("preview_sheet_id", None)
                        st.success("Fiche supprimée de la bibliothèque et du Storage.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Suppression impossible : {exc}")
    else:
        st.caption("Bibliothèque vide.")

import pandas as pd
import streamlit as st
from services.metadata import detect_metadata
from services.library import list_sheets, save_sheet
from services.matcher import search_library

st.set_page_config(page_title="Fiches techniques", page_icon="📄", layout="centered")

st.title("Fiches techniques")
st.caption("Créer un dossier à partir de fiches fabricants originales, sans les modifier.")

tab_build, tab_library = st.tabs(["Créer un dossier", "Bibliothèque"])

with tab_build:
    st.subheader("1. Saisir le contenu du dossier")
    st.write(
        "Ajoute directement les titres et les fiches techniques dans l'ordre souhaité. "
        "Une ligne = une page de titre ou une fiche technique."
    )

    if "manual_plan" not in st.session_state:
        st.session_state.manual_plan = pd.DataFrame(
            [
                {"Type": "Titre", "Désignation": ""},
                {"Type": "FT", "Désignation": ""},
            ]
        )

    plan = st.data_editor(
        st.session_state.manual_plan,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Type": st.column_config.SelectboxColumn(
                "Type",
                options=["Titre", "FT"],
                required=True,
                width="small",
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
        "L'ordre des lignes sera exactement l'ordre du futur PDF. "
        "Tu peux ajouter ou supprimer des lignes directement dans le tableau."
    )

    if st.button("Rechercher les fiches techniques", type="primary"):
        clean_plan = plan.copy()
        clean_plan["Désignation"] = clean_plan["Désignation"].fillna("").astype(str).str.strip()
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
                    "Score": "",
                    "Statut": "",
                    "technical_sheet_id": None,
                }

                if row["Type"] == "FT":
                    matches = search_library(row["Désignation"], sheets, limit=1) if sheets else []
                    if matches:
                        score, sheet = matches[0]
                        item["Fiche proposée"] = sheet.get("product_name", "")
                        item["Marque"] = sheet.get("brand", "") or ""
                        item["Score"] = score
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

    if "manual_results" in st.session_state:
        st.subheader("2. Vérifier les correspondances")

        display = pd.DataFrame(
            [
                {k: v for k, v in row.items() if k != "technical_sheet_id"}
                for row in st.session_state["manual_results"]
            ]
        )

        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Score": st.column_config.NumberColumn(
                    "Score",
                    format="%d %%",
                )
            },
        )

        ft_rows = [
            row for row in st.session_state["manual_results"]
            if row["Type"] == "FT"
        ]
        unresolved = [
            row for row in ft_rows
            if row["Statut"] != "Trouvée"
        ]

        if unresolved:
            st.warning(
                f"{len(unresolved)} fiche(s) doivent encore être confirmées ou ajoutées à la bibliothèque."
            )
        elif ft_rows:
            st.success(
                "Toutes les fiches techniques ont été trouvées. "
                "L'ordre est prêt pour la génération du PDF."
            )

with tab_library:
    st.subheader("Importer des fiches techniques")
    st.write(
        "Dépose un ou plusieurs PDF. Le système remplit automatiquement les informations "
        "à partir du fichier et du contenu lisible du PDF. Tu ne corriges que si nécessaire."
    )

    uploads = st.file_uploader(
        "Fiches PDF",
        type=["pdf"],
        accept_multiple_files=True,
        key="library_uploads",
    )

    if uploads:
        if "detected_sheets" not in st.session_state:
            st.session_state.detected_sheets = {}

        for pdf in uploads:
            key = f"{pdf.name}-{pdf.size}"
            if key not in st.session_state.detected_sheets:
                st.session_state.detected_sheets[key] = detect_metadata(
                    pdf.name,
                    pdf.getvalue(),
                )

            metadata = st.session_state.detected_sheets[key]

            with st.expander(f"{pdf.name}", expanded=True):
                metadata["product_name"] = st.text_input(
                    "Produit détecté",
                    value=metadata["product_name"],
                    key=f"name-{key}",
                )
                c1, c2 = st.columns(2)
                with c1:
                    metadata["brand"] = st.text_input(
                        "Marque détectée",
                        value=metadata["brand"],
                        key=f"brand-{key}",
                    )
                    metadata["reference"] = st.text_input(
                        "Référence détectée",
                        value=metadata["reference"],
                        key=f"ref-{key}",
                    )
                with c2:
                    metadata["category"] = st.text_input(
                        "Catégorie détectée",
                        value=metadata["category"],
                        key=f"cat-{key}",
                    )
                    metadata["version_label"] = st.text_input(
                        "Version / date",
                        value=metadata["version_label"],
                        key=f"version-{key}",
                    )

                aliases_value = ", ".join(metadata.get("aliases") or [])
                aliases_text = st.text_input(
                    "Alias proposés",
                    value=aliases_value,
                    key=f"aliases-{key}",
                )
                metadata["aliases"] = [
                    a.strip() for a in aliases_text.split(",") if a.strip()
                ]

                if st.button("Ajouter cette fiche à la bibliothèque", key=f"save-{key}"):
                    try:
                        save_sheet(metadata, pdf.name, pdf.getvalue())
                        st.success("Fiche ajoutée. Le PDF original a été stocké sans modification.")
                    except Exception as exc:
                        st.error(f"Impossible d'ajouter la fiche : {exc}")

    st.divider()
    st.subheader("Bibliothèque existante")
    try:
        sheets = list_sheets()
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

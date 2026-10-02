import streamlit as st
from services.document_reader import read_uploaded_document
from services.metadata import detect_metadata
from services.library import list_sheets, save_sheet
from services.matcher import search_library

st.set_page_config(page_title="Fiches techniques", page_icon="📄", layout="centered")

st.title("Fiches techniques")
st.caption("Créer un dossier à partir de fiches fabricants originales, sans les modifier.")

tab_build, tab_library = st.tabs(["Créer un dossier", "Bibliothèque"])

with tab_build:
    st.subheader("1. Importer le descriptif")
    source = st.file_uploader(
        "PDF, Word ou TXT",
        type=["pdf", "docx", "txt"],
        key="source_doc",
    )

    if source:
        try:
            text = read_uploaded_document(source)
            st.success("Descriptif lu.")
            with st.expander("Voir le texte extrait"):
                st.text_area("Texte", text, height=280, label_visibility="collapsed")

            st.subheader("2. Recherche test")
            query = st.text_input(
                "Produit à rechercher",
                placeholder="Ex. Sarlon Primeo 33",
            )
            if query:
                try:
                    results = search_library(query, list_sheets())
                    if results:
                        for score, sheet in results:
                            status = "Très probable" if score >= 90 else "À vérifier"
                            st.write(
                                f"**{sheet['product_name']}**"
                                + (f" — {sheet.get('brand')}" if sheet.get("brand") else "")
                                + f" — {score}% — {status}"
                            )
                    else:
                        st.warning("Aucune fiche dans la bibliothèque.")
                except Exception:
                    st.warning("La bibliothèque Supabase n'est pas encore connectée.")
        except Exception as exc:
            st.error(str(exc))

    st.info(
        "L'analyse automatique complète de la liste des titres et produits sera ajoutée "
        "après validation sur un descriptif réel."
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

        for i, pdf in enumerate(uploads):
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
                        st.error(
                            "Impossible d'ajouter la fiche pour le moment. "
                            f"Supabase doit d'abord être configuré. Détail : {exc}"
                        )

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
    except Exception:
        st.caption("La connexion Supabase sera configurée à l'étape suivante.")

import os

import streamlit as st
from supabase import create_client


def _get_secret(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value

    try:
        return st.secrets[name]
    except Exception as exc:
        raise RuntimeError(
            f"Configuration manquante : {name}. "
            "Ajoute cette variable dans les variables d'environnement Render."
        ) from exc


@st.cache_resource
def get_supabase():
    return create_client(
        _get_secret("SUPABASE_URL"),
        _get_secret("SUPABASE_KEY"),
    )

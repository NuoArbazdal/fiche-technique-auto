import os
from functools import lru_cache

from supabase import create_client


def _get_secret(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value

    try:
        import streamlit as st
        return st.secrets[name]
    except Exception as exc:
        raise RuntimeError(
            f"Configuration manquante : {name}. "
            "Ajoute cette variable dans les variables d'environnement."
        ) from exc


@lru_cache(maxsize=1)
def get_supabase():
    return create_client(
        _get_secret("SUPABASE_URL"),
        _get_secret("SUPABASE_KEY"),
    )

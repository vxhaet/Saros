import io
import tempfile

import pdfplumber
import pandas as pd
from pathlib import Path

from .storage import get_file


TABULAR_EXTENSIONS = {".xlsx", ".xls", ".csv"}
TEXT_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TABULAR_EXTENSIONS | TEXT_EXTENSIONS


def load_file_from_storage(file_id: str, file_name: str) -> pd.DataFrame:
    """Charge un fichier tabulaire depuis MongoDB (ou mémoire)."""
    content = get_file(file_id, file_name)
    if content is None:
        raise FileNotFoundError(
            f"Fichier introuvable dans le stockage : {file_id}/{file_name}"
        )

    suffix = Path(file_name).suffix.lower()
    if suffix not in TABULAR_EXTENSIONS:
        raise ValueError(f"Format non supporté pour le mode tabulaire : {suffix}")

    buf = io.BytesIO(content)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(buf)
    return pd.read_csv(buf)


def extract_text_from_pdf_storage(file_id: str, file_name: str) -> str:
    """Extrait le texte d'un PDF depuis MongoDB (ou mémoire)."""
    content = get_file(file_id, file_name)
    if content is None:
        raise FileNotFoundError(
            f"Fichier introuvable dans le stockage : {file_id}/{file_name}"
        )

    # pdfplumber a besoin d'un fichier sur disque → fichier temporaire
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        pages_text = []
        with pdfplumber.open(tmp.name) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
    return "\n".join(pages_text)


def is_text_file(file_name: str) -> bool:
    return Path(file_name).suffix.lower() in TEXT_EXTENSIONS


def extract_samples(df: pd.DataFrame, n: int = 3) -> dict[str, list[str]]:
    samples = {}
    for col in df.columns:
        non_null = df[col].dropna().head(n)
        samples[col] = [str(v) for v in non_null.tolist()]
    return samples

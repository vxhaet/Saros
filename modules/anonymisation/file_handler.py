import pdfplumber
import pandas as pd
from pathlib import Path


TABULAR_EXTENSIONS = {".xlsx", ".xls", ".csv"}
TEXT_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TABULAR_EXTENSIONS | TEXT_EXTENSIONS


def load_file(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    if path.suffix not in TABULAR_EXTENSIONS:
        raise ValueError(f"Format non supporté pour le mode tabulaire : {path.suffix}")
    if path.suffix in (".xlsx", ".xls"):
        return pd.read_excel(file_path)
    return pd.read_csv(file_path)


def extract_text_from_pdf(file_path: str) -> str:
    pages_text = []
    with pdfplumber.open(file_path) as pdf:
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


def resolve_file_path(storage_path: str, file_id: str, file_name: str) -> str:
    path = Path(storage_path) / file_id / file_name
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    return str(path)

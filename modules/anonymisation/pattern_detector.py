"""Détection de données sensibles par patterns (regex).

Couche 1 de la détection hybride : capture les formats structurés
connus avec une fiabilité élevée.
"""

import re


# Les patterns sont ordonnés du plus spécifique au plus général.
# Les patterns plus spécifiques sont testés en premier pour éviter
# qu'un pattern général ne capture un faux positif.
PATTERNS = [
    # --- IBAN ---
    {
        "category": "IBAN",
        "rgpdArticle": "Article 4",
        "label": "IBAN",
        "pattern": re.compile(
            r"[A-Z]{2}\d{2}(?:[\s]?\d{4}){2,7}"
        ),
    },
    # --- BIC/SWIFT ---
    {
        "category": "IBAN",
        "rgpdArticle": "Article 4",
        "label": "Code BIC/SWIFT",
        "pattern": re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"),
    },
    # --- Email ---
    {
        "category": "EMAIL",
        "rgpdArticle": "Article 4",
        "label": "Email",
        "pattern": re.compile(
            r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
        ),
    },
    # --- Téléphone (formats stricts) ---
    {
        "category": "TELEPHONE",
        "rgpdArticle": "Article 4",
        "label": "Téléphone",
        "pattern": re.compile(
            r"(?:\+\d{1,3}[\s.-]?)?\b0\d[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}\b"
        ),
    },
    # --- Numéro de sécurité sociale (NIR) ---
    {
        "category": "NIR",
        "rgpdArticle": "Article 4",
        "label": "Numéro de sécurité sociale",
        "pattern": re.compile(
            r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b"
        ),
    },
    # --- Numéros de TVA ---
    {
        "category": "ID_UNIQUE",
        "rgpdArticle": "Article 4",
        "label": "Numéro de TVA belge",
        "pattern": re.compile(r"\bBE[\s]?\d{4}[\s.]?\d{3}[\s.]?\d{3}\b"),
    },
    {
        "category": "ID_UNIQUE",
        "rgpdArticle": "Article 4",
        "label": "Numéro de TVA français",
        "pattern": re.compile(r"\bFR[\s]?\d{2}[\s]?\d{3}[\s]?\d{3}[\s]?\d{3}\b"),
    },
    # --- Communication structurée belge ---
    {
        "category": "ID_UNIQUE",
        "rgpdArticle": "Article 4",
        "label": "Communication structurée belge",
        "pattern": re.compile(r"\+{3}\d{3}/\d{4}/\d{5}\+{3}"),
    },
]

# Mots courants à ne pas capturer comme BIC (faux positifs)
BIC_EXCLUSIONS = {
    "HTVA", "TVAC", "SPRL", "BVBA", "ASBL", "DATE", "BASE", "TAUX",
    "TAXE", "IBAN", "BELGIQUE", "FRANCE", "TOTAL", "SUPPORT", "MONTANT",
    "FACTURE", "QUANTITE", "COMMUNICATION",
}


def detect_by_patterns(text: str) -> list[dict]:
    """Détecte les données sensibles par patterns regex.

    Retourne une liste de dicts avec : value, category, rgpdArticle, label.
    """
    results = []
    seen_values = set()
    # Positions déjà couvertes par un match (pour éviter les chevauchements)
    covered_ranges: list[tuple[int, int]] = []

    for pat_def in PATTERNS:
        for match in pat_def["pattern"].finditer(text):
            value = match.group().strip()
            start, end = match.start(), match.end()

            # Vérifier que cette position n'est pas déjà couverte
            if any(s <= start and end <= e for s, e in covered_ranges):
                continue

            # Filtrer les faux positifs BIC
            if pat_def["label"] == "Code BIC/SWIFT" and value in BIC_EXCLUSIONS:
                continue

            if value not in seen_values:
                seen_values.add(value)
                covered_ranges.append((start, end))
                results.append(
                    {
                        "value": value,
                        "category": pat_def["category"],
                        "rgpdArticle": pat_def["rgpdArticle"],
                        "label": pat_def["label"],
                    }
                )

    return results

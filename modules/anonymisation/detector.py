import json

import httpx

from .config import Settings
from .models import AnonymizationStrategy, DetectedEntity, DetectedField
from .pattern_detector import detect_by_patterns
from .rgpd import get_categories_for_prompt


DETECTION_SYSTEM_PROMPT = """\
Tu es un expert en protection des données personnelles (RGPD).
Tu analyses des données tabulaires pour identifier les colonnes contenant des données personnelles ou sensibles.

Pour chaque colonne sensible détectée, tu dois :
1. Identifier la catégorie RGPD correspondante parmi les codes fournis.
2. Recommander une stratégie d'anonymisation selon le contexte de la demande :
   - "placeholder" : remplacement par un placeholder typé (ex: [NOM_1]).
     A utiliser quand les données seront envoyées vers un LLM externe
     et doivent rester lisibles et compréhensibles dans leur contexte.
   - "encryption" : chiffrement réversible.
     A utiliser quand les données doivent pouvoir être ré-identifiées
     ultérieurement, ou servent d'identifiant de jointure entre systèmes.
3. Justifier ta recommandation en une phrase.

Tu dois répondre UNIQUEMENT en JSON valide, sans texte autour :
{
  "detectedFields": [
    {
      "field": "nom_de_la_colonne",
      "category": "CODE_CATEGORIE",
      "rgpdArticle": "Article X",
      "recommendedStrategy": "placeholder|encryption",
      "justification": "Explication courte"
    }
  ]
}

Si aucune colonne sensible n'est détectée, retourne :
{"detectedFields": []}
"""


def build_detection_prompt(
    columns: list[str],
    samples: dict[str, list[str]],
    user_message: str,
) -> str:
    categories_text = get_categories_for_prompt()

    columns_detail = []
    for col in columns:
        col_samples = samples.get(col, [])
        columns_detail.append(f"  - {col} : {col_samples}")

    return (
        f'Contexte de la demande utilisateur : "{user_message}"\n\n'
        f"Catégories RGPD disponibles :\n{categories_text}\n\n"
        f"Colonnes du fichier avec exemples de valeurs :\n"
        f"{chr(10).join(columns_detail)}\n\n"
        f"Analyse chaque colonne et identifie celles qui contiennent "
        f"des données personnelles ou sensibles au sens du RGPD.\n"
        f"Pour chaque colonne sensible, recommande une stratégie "
        f"d'anonymisation adaptée au contexte de la demande."
    )


async def detect_sensitive_fields(
    columns: list[str],
    samples: dict[str, list[str]],
    user_message: str,
    settings: Settings,
) -> list[DetectedField]:
    prompt = build_detection_prompt(columns, samples, user_message)
    raw_response = await call_local_llm(prompt, settings)
    return parse_detection_response(raw_response, samples)


TEXT_DETECTION_SYSTEM_PROMPT = """\
Tu es un expert en protection des données personnelles (RGPD).
Tu analyses un texte en langage naturel pour identifier les données \
personnelles ou sensibles qu'il contient.

NOTE : Les données structurées (IBAN, emails, numéros de TVA, téléphones, \
numéros de sécurité sociale) sont DÉJÀ détectées par un autre système. \
Tu n'as PAS besoin de les chercher.

TON RÔLE est de détecter ce que les regex ne voient pas :
- Noms de PERSONNES (nom, prénom, nom complet)
- Noms d'ENTREPRISES, de sociétés, de cabinets, de consulting
- ADRESSES postales (rue, numéro, code postal, ville, pays)
- Descriptions ou intitulés qui révèlent l'identité (ex: "Consulting Vincent D.")
- Toute autre donnée identifiante non structurée

IMPORTANT — Analyse contextuelle :
- Comprends L'INTENTION de la demande utilisateur.
- Une donnée identifiante (nom, entreprise, adresse) doit TOUJOURS être anonymisée.
- Une donnée NÉCESSAIRE au traitement (montant pour un calcul, date pour un tri, \
  quantité, taux) ne doit PAS être anonymisée si, une fois les identifiants \
  supprimés, elle ne permet plus d'identifier une personne.

Exemple sur une facture :
- "Facture de ACME Corp, 12 rue de Paris, pour Jean Martin. Total: 5000€"
- "ACME Corp" → entreprise cliente, à anonymiser (NOM)
- "Jean Martin" → personne, à anonymiser (NOM)
- "12 rue de Paris" → adresse, à anonymiser (ADRESSE)
- "5000€" → montant nécessaire au calcul → NE PAS anonymiser

Pour chaque donnée détectée, tu dois :
1. Extraire la valeur EXACTE telle qu'elle apparaît dans le texte.
2. Identifier la catégorie RGPD correspondante.
3. Recommander "placeholder" (lisible par LLM externe) ou "encryption" (réversible).
4. Justifier en une phrase.

Réponds UNIQUEMENT en JSON valide :
{
  "detectedEntities": [
    {
      "value": "valeur exacte du texte",
      "category": "CODE_CATEGORIE",
      "rgpdArticle": "Article X",
      "recommendedStrategy": "placeholder|encryption",
      "justification": "Explication courte"
    }
  ]
}

Si rien à détecter : {"detectedEntities": []}
"""


def build_text_detection_prompt(user_message: str) -> str:
    categories_text = get_categories_for_prompt()
    return (
        f"Catégories RGPD disponibles :\n{categories_text}\n\n"
        f"Texte à analyser :\n\"{user_message}\"\n\n"
        f"Identifie toutes les données personnelles ou sensibles "
        f"présentes dans ce texte. Extrais la valeur exacte de chaque "
        f"donnée telle qu'elle apparaît dans le texte."
    )


async def detect_sensitive_entities(
    user_message: str,
    settings: Settings,
) -> list[DetectedEntity]:
    # Couche 1 : détection par patterns (regex)
    pattern_results = detect_by_patterns(user_message)
    pattern_entities = [
        DetectedEntity(
            value=r["value"],
            category=r["category"],
            rgpdArticle=r["rgpdArticle"],
            recommendedStrategy=AnonymizationStrategy.ENCRYPTION,
            justification=f"Détecté automatiquement ({r['label']}).",
        )
        for r in pattern_results
    ]

    # Couche 2 : détection par LLM local (noms, entreprises, adresses)
    llm_entities = []
    try:
        prompt = build_text_detection_prompt(user_message)
        raw_response = await call_local_llm(
            prompt, settings, system_prompt=TEXT_DETECTION_SYSTEM_PROMPT
        )
        llm_entities = parse_entity_response(raw_response)
    except (httpx.ConnectError, httpx.ReadTimeout):
        # Ollama non disponible — on continue avec les regex seuls
        pass

    # Fusion : LLM d'abord (placeholders lisibles), puis patterns (encryption)
    seen_values = set()
    merged = []

    for entity in llm_entities:
        if entity.value not in seen_values:
            seen_values.add(entity.value)
            merged.append(entity)

    for entity in pattern_entities:
        if entity.value not in seen_values:
            seen_values.add(entity.value)
            merged.append(entity)

    return merged


def parse_entity_response(raw_response: str) -> list[DetectedEntity]:
    data = json.loads(raw_response)
    entities = []
    for item in data.get("detectedEntities", []):
        entity = DetectedEntity(
            value=item["value"],
            category=item["category"],
            rgpdArticle=item["rgpdArticle"],
            recommendedStrategy=AnonymizationStrategy(item["recommendedStrategy"]),
            justification=item["justification"],
        )
        entities.append(entity)
    return entities


async def call_local_llm(prompt: str, settings: Settings, system_prompt: str = DETECTION_SYSTEM_PROMPT) -> str:
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


def parse_detection_response(
    raw_response: str,
    samples: dict[str, list[str]],
) -> list[DetectedField]:
    data = json.loads(raw_response)
    fields = []
    for item in data.get("detectedFields", []):
        field = DetectedField(
            field=item["field"],
            category=item["category"],
            rgpdArticle=item["rgpdArticle"],
            samples=samples.get(item["field"], []),
            recommendedStrategy=AnonymizationStrategy(item["recommendedStrategy"]),
            justification=item["justification"],
        )
        fields.append(field)
    return fields

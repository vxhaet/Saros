"""Couche de stockage pour les requêtes en attente et les mappings de conversation.

Deux modes :
- En mémoire (défaut) : pour le dev local
- MongoDB : pour la production (SAROS_ANON_MONGO_URI configuré)
"""

import json
import pickle
from datetime import datetime, timezone

from .config import settings

_mongo_client = None
_db = None


def _get_db():
    global _mongo_client, _db
    if _db is not None:
        return _db
    if not settings.mongo_uri:
        return None
    import certifi
    from pymongo import MongoClient

    _mongo_client = MongoClient(
        settings.mongo_uri,
        tls=True,
        tlsCAFile=certifi.where(),
        tlsAllowInvalidCertificates=False,
        serverSelectionTimeoutMS=10000,
    )
    _db = _mongo_client[settings.mongo_db_name]
    return _db


# ── Fallback en mémoire ─────────────────────────────────────────────

_memory_pending: dict[str, dict] = {}
_memory_conversations: dict[str, dict] = {}


# ── Requêtes en attente (entre detect et execute) ────────────────────


def save_pending_request(request_id: str, data: dict) -> None:
    db = _get_db()
    if db is None:
        _memory_pending[request_id] = data
        return

    # Sérialiser les objets non-JSON (DataFrame) en pickle
    serializable = {}
    for key, value in data.items():
        try:
            json.dumps(value)
            serializable[key] = value
        except (TypeError, ValueError):
            serializable[key] = {
                "__pickle__": True,
                "data": pickle.dumps(value).hex(),
            }

    db.pending_requests.update_one(
        {"_id": request_id},
        {
            "$set": {
                "data": serializable,
                "created_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


def get_pending_request(request_id: str) -> dict | None:
    db = _get_db()
    if db is None:
        return _memory_pending.get(request_id)

    doc = db.pending_requests.find_one({"_id": request_id})
    if not doc:
        return None

    data = doc["data"]
    result = {}
    for key, value in data.items():
        if isinstance(value, dict) and value.get("__pickle__"):
            result[key] = pickle.loads(bytes.fromhex(value["data"]))
        else:
            result[key] = value

    return result


def delete_pending_request(request_id: str) -> None:
    db = _get_db()
    if db is None:
        _memory_pending.pop(request_id, None)
        return
    db.pending_requests.delete_one({"_id": request_id})


# ── Mappings de conversation (persistance multi-messages) ────────────


def save_conversation_mappings(conversation_id: str, mappings: dict) -> None:
    db = _get_db()
    if db is None:
        _memory_conversations[conversation_id] = mappings
        return

    db.conversation_mappings.update_one(
        {"_id": conversation_id},
        {
            "$set": {
                "mappings": mappings,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


def get_conversation_mappings(conversation_id: str) -> dict | None:
    db = _get_db()
    if db is None:
        return _memory_conversations.get(conversation_id)

    doc = db.conversation_mappings.find_one({"_id": conversation_id})
    if not doc:
        return None
    return doc["mappings"]


# ── Journal d'anonymisation (table lisible pour reporting) ───────────

_memory_audit: list[dict] = []


def save_anonymisation_audit(
    conversation_id: str,
    request_id: str,
    user_id: str,
    mappings: dict,
) -> None:
    """Enregistre chaque anonymisation dans une table lisible.

    Chaque ligne = une correspondance valeur originale ↔ valeur anonymisée.
    Utilisable pour le reporting réglementaire (RGPD).
    """
    db = _get_db()
    now = datetime.now(timezone.utc)

    records = []

    # Placeholders
    placeholder_mappings = mappings.get("placeholder_mappings", {})
    for category, items in placeholder_mappings.items():
        for placeholder, original_value in items.items():
            records.append({
                "conversation_id": conversation_id,
                "request_id": request_id,
                "user_id": user_id,
                "categorie": category,
                "valeur_originale": original_value,
                "valeur_anonymisee": placeholder,
                "strategie": "placeholder",
                "created_at": now,
            })

    # Chiffrements — on ne stocke pas les valeurs chiffrées individuellement
    # car elles sont réversibles via la clé. On enregistre juste la clé.
    encryption_key = mappings.get("encryption_key")
    if encryption_key:
        records.append({
            "conversation_id": conversation_id,
            "request_id": request_id,
            "user_id": user_id,
            "categorie": "_ENCRYPTION_KEY",
            "valeur_originale": "(clé de chiffrement)",
            "valeur_anonymisee": encryption_key,
            "strategie": "encryption",
            "created_at": now,
        })

    if db is None:
        _memory_audit.extend(records)
        return

    if records:
        db.anonymisation_audit.insert_many(records)


def get_anonymisation_audit(
    conversation_id: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Récupère le journal d'anonymisation pour le reporting.

    Filtrable par conversation_id et/ou user_id.
    """
    db = _get_db()

    if db is None:
        results = _memory_audit
        if conversation_id:
            results = [r for r in results if r["conversation_id"] == conversation_id]
        if user_id:
            results = [r for r in results if r["user_id"] == user_id]
        return results[:limit]

    query = {}
    if conversation_id:
        query["conversation_id"] = conversation_id
    if user_id:
        query["user_id"] = user_id

    cursor = db.anonymisation_audit.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit)

    return list(cursor)

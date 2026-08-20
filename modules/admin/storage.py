"""Stockage pour les tables membres, groupes et relations."""

import uuid
from datetime import datetime, timezone

from ..anonymisation.storage import _get_db


# ── Fallback mémoire ─────────────────────────────────────────────────

_memory_members: dict[str, dict] = {}
_memory_groups: dict[str, dict] = {}
_memory_relations: list[dict] = []
_memory_pending_approvals: dict[str, dict] = {}


# ── Membres ──────────────────────────────────────────────────────────


def save_member(
    user_id: str,
    nom: str,
    prenom: str,
    langue: str,
    password: str,
    group_id: str | None = None,
) -> None:
    db = _get_db()
    now = datetime.now(timezone.utc)

    doc = {
        "nom": nom,
        "prenom": prenom,
        "langue": langue,
        "password": password,
        "groupId": group_id,
        "created_at": now,
    }

    if db is None:
        _memory_members[user_id] = {"_id": user_id, **doc}
        return

    db.members.update_one(
        {"_id": user_id},
        {"$set": doc},
        upsert=True,
    )


def get_member(user_id: str) -> dict | None:
    db = _get_db()

    if db is None:
        m = _memory_members.get(user_id)
        if m:
            return {**m, "userId": m["_id"]}
        return None

    doc = db.members.find_one({"_id": user_id})
    if not doc:
        return None
    return {**doc, "userId": doc["_id"]}


def update_member(user_id: str, updates: dict) -> bool:
    db = _get_db()

    if db is None:
        if user_id not in _memory_members:
            return False
        _memory_members[user_id].update(updates)
        return True

    result = db.members.update_one({"_id": user_id}, {"$set": updates})
    return result.modified_count > 0


def delete_member(user_id: str) -> bool:
    db = _get_db()

    if db is None:
        if user_id in _memory_members:
            del _memory_members[user_id]
            return True
        return False

    result = db.members.delete_one({"_id": user_id})
    return result.deleted_count > 0


# ── Groupes ──────────────────────────────────────────────────────────


def create_group(
    nom: str,
    choix_llm: str,
    cle_api: str,
    search_web: bool,
    validation_anonym: bool,
) -> str:
    db = _get_db()
    group_id = f"grp-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    doc = {
        "nom": nom,
        "choixLLM": choix_llm,
        "cleAPI": cle_api,
        "searchWeb": search_web,
        "validationAnonym": validation_anonym,
        "created_at": now,
    }

    if db is None:
        _memory_groups[group_id] = {"_id": group_id, **doc}
    else:
        db.groups.insert_one({"_id": group_id, **doc})

    return group_id


def get_group(group_id: str) -> dict | None:
    db = _get_db()

    if db is None:
        g = _memory_groups.get(group_id)
        if g:
            return {**g, "groupId": g["_id"]}
        return None

    doc = db.groups.find_one({"_id": group_id})
    if not doc:
        return None
    return {**doc, "groupId": doc["_id"]}


def update_group(group_id: str, updates: dict) -> bool:
    db = _get_db()

    if db is None:
        if group_id not in _memory_groups:
            return False
        _memory_groups[group_id].update(updates)
        return True

    result = db.groups.update_one({"_id": group_id}, {"$set": updates})
    return result.modified_count > 0


def delete_group(group_id: str) -> bool:
    db = _get_db()

    if db is None:
        if group_id in _memory_groups:
            del _memory_groups[group_id]
            return True
        return False

    result = db.groups.delete_one({"_id": group_id})
    return result.deleted_count > 0


# ── Relations (membre ↔ groupe) ──────────────────────────────────────


def add_relation(user_id: str, group_id: str, role: str = "member") -> None:
    """Ajoute un lien membre ↔ groupe. role = 'admin' ou 'member'."""
    db = _get_db()
    now = datetime.now(timezone.utc)

    doc = {
        "userId": user_id,
        "groupId": group_id,
        "role": role,
        "created_at": now,
    }

    if db is None:
        _memory_relations.append(doc)
        return

    # Éviter les doublons
    existing = db.relations.find_one({"userId": user_id, "groupId": group_id})
    if existing:
        db.relations.update_one(
            {"_id": existing["_id"]},
            {"$set": {"role": role}},
        )
    else:
        db.relations.insert_one(doc)


def get_relations_for_user(user_id: str) -> list[dict]:
    db = _get_db()

    if db is None:
        return [r for r in _memory_relations if r["userId"] == user_id]

    return list(db.relations.find({"userId": user_id}, {"_id": 0}))


def get_relations_for_group(group_id: str) -> list[dict]:
    db = _get_db()

    if db is None:
        return [r for r in _memory_relations if r["groupId"] == group_id]

    return list(db.relations.find({"groupId": group_id}, {"_id": 0}))


def get_group_admins(group_id: str) -> list[dict]:
    """Retourne les membres admin d'un groupe."""
    db = _get_db()

    if db is None:
        admin_ids = [
            r["userId"]
            for r in _memory_relations
            if r["groupId"] == group_id and r["role"] == "admin"
        ]
        return [_memory_members[uid] for uid in admin_ids if uid in _memory_members]

    admin_relations = db.relations.find({"groupId": group_id, "role": "admin"})
    admins = []
    for rel in admin_relations:
        member = db.members.find_one({"_id": rel["userId"]})
        if member:
            admins.append({**member, "userId": member["_id"]})
    return admins


def remove_relation(user_id: str, group_id: str) -> bool:
    db = _get_db()

    if db is None:
        before = len(_memory_relations)
        _memory_relations[:] = [
            r
            for r in _memory_relations
            if not (r["userId"] == user_id and r["groupId"] == group_id)
        ]
        return len(_memory_relations) < before

    result = db.relations.delete_one({"userId": user_id, "groupId": group_id})
    return result.deleted_count > 0


# ── Demandes d'approbation en attente ────────────────────────────────


def save_pending_approval(
    approval_id: str,
    user_id: str,
    group_id: str,
    member_data: dict,
) -> None:
    db = _get_db()
    now = datetime.now(timezone.utc)

    doc = {
        "userId": user_id,
        "groupId": group_id,
        "memberData": member_data,
        "status": "pending",
        "created_at": now,
    }

    if db is None:
        _memory_pending_approvals[approval_id] = doc
        return

    db.pending_approvals.update_one(
        {"_id": approval_id},
        {"$set": doc},
        upsert=True,
    )


def get_pending_approval(approval_id: str) -> dict | None:
    db = _get_db()

    if db is None:
        return _memory_pending_approvals.get(approval_id)

    doc = db.pending_approvals.find_one({"_id": approval_id})
    if not doc:
        return None
    return doc


def get_pending_approvals_for_group(group_id: str) -> list[dict]:
    """Retourne toutes les demandes en attente pour un groupe."""
    db = _get_db()

    if db is None:
        return [
            {"approvalId": k, **v}
            for k, v in _memory_pending_approvals.items()
            if v["groupId"] == group_id and v["status"] == "pending"
        ]

    docs = db.pending_approvals.find({"groupId": group_id, "status": "pending"})
    return [
        {
            "approvalId": doc["_id"],
            "userId": doc["userId"],
            "groupId": doc["groupId"],
            "memberData": doc["memberData"],
            "created_at": doc.get("created_at"),
        }
        for doc in docs
    ]


def delete_pending_approval(approval_id: str) -> None:
    db = _get_db()

    if db is None:
        _memory_pending_approvals.pop(approval_id, None)
        return

    db.pending_approvals.delete_one({"_id": approval_id})

"""Endpoints d'administration (boîte orange).

Gestion des membres, groupes et relations.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from ..anonymisation.config import settings
from ..services.auth import create_token, verify_token
from ..services.email_service import send_approval_email
from .models import ApprovalResponse, RegisterRequest, RegisterResponse
from .storage import (
    add_relation,
    create_group,
    delete_member,
    delete_pending_approval,
    get_group,
    get_group_admins,
    get_member,
    get_pending_approval,
    get_relations_for_group,
    get_relations_for_user,
    remove_relation,
    save_member,
    save_pending_approval,
    update_group,
    update_member,
)

router = APIRouter(prefix="/admin", tags=["Administration"])


# ── Register ─────────────────────────────────────────────────────────


@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest):
    """Inscription d'un nouveau membre.

    Deux cas exclusifs :
    - joinGroupId fourni : demande à rejoindre un groupe existant (approbation admin requise)
    - newGroup fourni : crée un nouveau groupe (le membre devient admin)
    """
    # Validation : pas les deux en même temps
    if request.joinGroupId and request.newGroup:
        raise HTTPException(
            status_code=400,
            detail="Impossible de rejoindre un groupe ET d'en créer un en même temps.",
        )
    if not request.joinGroupId and not request.newGroup:
        raise HTTPException(
            status_code=400,
            detail="Vous devez soit rejoindre un groupe (joinGroupId) soit en créer un (newGroup).",
        )

    # Vérifier que le membre n'existe pas déjà
    existing = get_member(request.member.userId)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"L'utilisateur '{request.member.userId}' existe déjà.",
        )

    if request.newGroup:
        return _register_new_group(request)
    return _register_join_group(request)


def _register_new_group(request: RegisterRequest) -> RegisterResponse:
    """Cas 2 : le membre crée un nouveau groupe."""
    group = request.newGroup
    member = request.member

    # 1. Créer le groupe
    group_id = create_group(
        nom=group.nom,
        choix_llm=group.choixLLM,
        cle_api=group.cleAPI,
        search_web=group.searchWeb,
        validation_anonym=group.validationAnonym,
    )

    # 2. Créer le membre
    save_member(
        user_id=member.userId,
        nom=member.nom,
        prenom=member.prenom,
        langue=member.langue,
        password=member.password,
        group_id=group_id,
    )

    # 3. Créer la relation (le créateur est admin)
    add_relation(member.userId, group_id, role="admin")

    # 4. Aussi enregistrer dans la table users (pour le login)
    from ..anonymisation.storage import save_user
    save_user(member.userId, member.password, member.userId)

    return RegisterResponse(
        status="completed",
        userId=member.userId,
        groupId=group_id,
        message=f"Groupe '{group.nom}' créé. Vous en êtes l'administrateur.",
    )


def _register_join_group(request: RegisterRequest) -> RegisterResponse:
    """Cas 1 : le membre demande à rejoindre un groupe existant."""
    member = request.member
    group_id = request.joinGroupId

    # Vérifier que le groupe existe
    group = get_group(group_id)
    if not group:
        raise HTTPException(
            status_code=404,
            detail=f"Groupe '{group_id}' introuvable.",
        )

    # Créer une demande d'approbation
    approval_id = uuid.uuid4().hex
    save_pending_approval(
        approval_id=approval_id,
        user_id=member.userId,
        group_id=group_id,
        member_data={
            "nom": member.nom,
            "prenom": member.prenom,
            "langue": member.langue,
            "password": member.password,
        },
    )

    # Envoyer un email aux admins du groupe
    admins = get_group_admins(group_id)
    approval_url = f"{settings.base_url}/admin/approve/{approval_id}"
    reject_url = f"{settings.base_url}/admin/reject/{approval_id}"

    for admin in admins:
        admin_email = admin.get("userId") or admin.get("_id")
        admin_name = f"{admin.get('prenom', '')} {admin.get('nom', '')}".strip()
        send_approval_email(
            admin_email=admin_email,
            admin_name=admin_name,
            requester_name=f"{member.prenom} {member.nom}",
            requester_email=member.userId,
            group_name=group["nom"],
            approval_url=approval_url,
            reject_url=reject_url,
        )

    return RegisterResponse(
        status="pending_approval",
        userId=member.userId,
        groupId=group_id,
        message=(
            f"Demande envoyée aux administrateurs du groupe '{group['nom']}'. "
            "Vous recevrez une confirmation par email."
        ),
    )


# ── Approbation / Rejet ──────────────────────────────────────────────


@router.get("/approve/{approval_id}", response_model=ApprovalResponse)
async def approve_member(approval_id: str):
    """Approuve une demande d'adhésion à un groupe."""
    pending = get_pending_approval(approval_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Demande introuvable ou déjà traitée.")

    member_data = pending["memberData"]
    user_id = pending["userId"]
    group_id = pending["groupId"]

    # Créer le membre
    save_member(
        user_id=user_id,
        nom=member_data["nom"],
        prenom=member_data["prenom"],
        langue=member_data["langue"],
        password=member_data["password"],
        group_id=group_id,
    )

    # Créer la relation (rôle membre)
    add_relation(user_id, group_id, role="member")

    # Enregistrer dans la table users (pour le login)
    from ..anonymisation.storage import save_user
    save_user(user_id, member_data["password"], user_id)

    # Supprimer la demande
    delete_pending_approval(approval_id)

    group = get_group(group_id)
    group_name = group["nom"] if group else group_id

    return ApprovalResponse(
        status="approved",
        message=f"{member_data['prenom']} {member_data['nom']} a été ajouté au groupe '{group_name}'.",
    )


@router.get("/reject/{approval_id}", response_model=ApprovalResponse)
async def reject_member(approval_id: str):
    """Rejette une demande d'adhésion à un groupe."""
    pending = get_pending_approval(approval_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Demande introuvable ou déjà traitée.")

    delete_pending_approval(approval_id)

    return ApprovalResponse(
        status="rejected",
        message="La demande a été refusée.",
    )


# ── CRUD Membres ─────────────────────────────────────────────────────


@router.get("/members/{user_id}")
async def get_member_info(
    user_id: str,
    current_user: str = Depends(verify_token),
):
    """Récupère les infos d'un membre."""
    member = get_member(user_id)
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    member.pop("password", None)
    member.pop("_id", None)
    return member


@router.put("/members/{user_id}")
async def update_member_info(
    user_id: str,
    updates: dict,
    current_user: str = Depends(verify_token),
):
    """Met à jour les infos d'un membre."""
    updates.pop("password", None)  # Ne pas modifier le password via cette route
    updates.pop("_id", None)
    if not update_member(user_id, updates):
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    return {"status": "updated"}


@router.delete("/members/{user_id}")
async def delete_member_endpoint(
    user_id: str,
    current_user: str = Depends(verify_token),
):
    """Supprime un membre."""
    if not delete_member(user_id):
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    return {"status": "deleted"}


# ── CRUD Groupes ─────────────────────────────────────────────────────


@router.get("/groups/{group_id}")
async def get_group_info(
    group_id: str,
    current_user: str = Depends(verify_token),
):
    """Récupère les infos d'un groupe."""
    group = get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable.")
    group.pop("_id", None)
    group.pop("cleAPI", None)  # Ne pas exposer la clé API
    return group


@router.put("/groups/{group_id}")
async def update_group_info(
    group_id: str,
    updates: dict,
    current_user: str = Depends(verify_token),
):
    """Met à jour les infos d'un groupe. Réservé aux admins du groupe."""
    # Vérifier que l'utilisateur est admin
    admins = get_group_admins(group_id)
    admin_ids = [a.get("userId") or a.get("_id") for a in admins]
    if current_user not in admin_ids:
        raise HTTPException(
            status_code=403,
            detail="Seuls les administrateurs du groupe peuvent modifier ses paramètres.",
        )

    updates.pop("_id", None)
    if not update_group(group_id, updates):
        raise HTTPException(status_code=404, detail="Groupe introuvable.")
    return {"status": "updated"}


@router.get("/groups/{group_id}/members")
async def list_group_members(
    group_id: str,
    current_user: str = Depends(verify_token),
):
    """Liste les membres d'un groupe."""
    relations = get_relations_for_group(group_id)
    members = []
    for rel in relations:
        member = get_member(rel["userId"])
        if member:
            member.pop("password", None)
            member.pop("_id", None)
            member["role"] = rel["role"]
            members.append(member)
    return {"groupId": group_id, "members": members}


# ── CRUD Relations ───────────────────────────────────────────────────


@router.delete("/relations/{user_id}/{group_id}")
async def remove_member_from_group(
    user_id: str,
    group_id: str,
    current_user: str = Depends(verify_token),
):
    """Retire un membre d'un groupe. Réservé aux admins."""
    admins = get_group_admins(group_id)
    admin_ids = [a.get("userId") or a.get("_id") for a in admins]
    if current_user not in admin_ids:
        raise HTTPException(
            status_code=403,
            detail="Seuls les administrateurs peuvent retirer des membres.",
        )

    if not remove_relation(user_id, group_id):
        raise HTTPException(status_code=404, detail="Relation introuvable.")
    return {"status": "removed"}

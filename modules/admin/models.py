from pydantic import BaseModel


# ── Membres ──────────────────────────────────────────────────────────


class MemberCreate(BaseModel):
    nom: str
    prenom: str
    userId: str  # adresse email obligatoire
    langue: str = "fr"
    password: str


# ── Groupes ──────────────────────────────────────────────────────────


class GroupCreate(BaseModel):
    nom: str
    choixLLM: str = "claude-sonnet-4-6"
    cleAPI: str
    searchWeb: bool = True
    validationAnonym: bool = True


# ── Register ─────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    member: MemberCreate
    # Cas 1 : rejoindre un groupe existant
    joinGroupId: str | None = None
    # Cas 2 : créer un nouveau groupe
    newGroup: GroupCreate | None = None


class RegisterResponse(BaseModel):
    status: str
    userId: str
    groupId: str | None = None
    message: str


# ── Approbation ──────────────────────────────────────────────────────


class ApprovalResponse(BaseModel):
    status: str
    message: str

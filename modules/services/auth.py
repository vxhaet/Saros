"""Authentification JWT.

- GET /login?user=xxx&password=xxx → retourne un token JWT
- Toutes les autres routes vérifient le token via le header Authorization: Bearer <token>
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .storage import get_user, save_user

security = HTTPBearer()


def create_token(user_id: str) -> str:
    """Crée un token JWT pour un utilisateur authentifié."""
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=settings.jwt_expiration_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Vérifie le Bearer token et retourne le user_id.

    À utiliser comme dépendance FastAPI sur les routes protégées.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré. Reconnectez-vous via /login.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide.",
        )


def authenticate_user(user: str, password: str) -> str | None:
    """Vérifie les credentials et retourne le user_id si OK."""
    stored = get_user(user)
    if not stored:
        return None
    if stored["password"] != password:
        return None
    return stored["user_id"]


def register_user(user: str, password: str) -> str:
    """Enregistre un nouvel utilisateur. Retourne le user_id."""
    existing = get_user(user)
    if existing:
        raise ValueError(f"L'utilisateur '{user}' existe déjà.")
    user_id = user
    save_user(user, password, user_id)
    return user_id

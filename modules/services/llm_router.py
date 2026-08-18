import httpx
from cryptography.fernet import Fernet

from ..anonymisation.config import Settings


# Mapping des providers par préfixe de modèle
PROVIDER_MAP = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
}


def resolve_provider(target_llm: str) -> str:
    for prefix, provider in PROVIDER_MAP.items():
        if target_llm.startswith(prefix):
            return provider
    raise ValueError(
        f"LLM '{target_llm}' non reconnu. "
        f"Modèles supportés : claude-*, gpt-*, o1-*, o3-*, o4-*"
    )


async def send_to_llm(
    content: str,
    target_llm: str,
    settings: Settings,
    system_prompt: str | None = None,
) -> str:
    provider = resolve_provider(target_llm)

    if provider == "anthropic":
        return await _send_anthropic(content, target_llm, settings, system_prompt)
    elif provider == "openai":
        return await _send_openai(content, target_llm, settings, system_prompt)

    raise ValueError(f"Provider '{provider}' non implémenté.")


async def _send_anthropic(
    content: str,
    model: str,
    settings: Settings,
    system_prompt: str | None,
) -> str:
    if not settings.anthropic_api_key:
        raise ValueError("Clé API Anthropic non configurée (SAROS_ANON_ANTHROPIC_API_KEY).")

    messages = [{"role": "user", "content": content}]

    body = {
        "model": model,
        "max_tokens": 4096,
        "messages": messages,
    }
    if system_prompt:
        body["system"] = system_prompt

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]


async def _send_openai(
    content: str,
    model: str,
    settings: Settings,
    system_prompt: str | None,
) -> str:
    if not settings.openai_api_key:
        raise ValueError("Clé API OpenAI non configurée (SAROS_ANON_OPENAI_API_KEY).")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content})

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def deanonymize(text: str, mappings: dict) -> str:
    result = text

    # Remplacer les placeholders par les valeurs originales
    placeholder_mappings = mappings.get("placeholder_mappings", {})
    for _category, mapping in placeholder_mappings.items():
        for placeholder, original_value in mapping.items():
            result = result.replace(placeholder, original_value)

    # Déchiffrer les valeurs chiffrées si une clé est fournie
    encryption_key = mappings.get("encryption_key")
    if encryption_key:
        fernet = Fernet(encryption_key.encode())
        # Chercher les tokens Fernet dans le texte (commencent par gAAAAA)
        import re

        fernet_pattern = re.compile(r"gAAAAA[A-Za-z0-9_-]+=*")
        for match in fernet_pattern.finditer(result):
            token = match.group()
            try:
                decrypted = fernet.decrypt(token.encode()).decode()
                result = result.replace(token, decrypted)
            except Exception:
                pass

    return result

"""Service d'appel au LLM local (brique verte).

Supporte deux backends :
- Ollama (local ou serveur dédié)
- RunPod Serverless (GPU cloud EU, auto-shutdown)

Le backend est choisi automatiquement selon la configuration :
- Si SAROS_ANON_RUNPOD_API_KEY est défini → RunPod
- Sinon → Ollama
"""

import httpx

from ..anonymisation.config import Settings


async def call_local_llm(
    prompt: str,
    settings: Settings,
    system_prompt: str = "",
) -> str:
    """Appelle le LLM local (Ollama ou RunPod) et retourne la réponse."""
    if settings.runpod_api_key and settings.runpod_endpoint_id:
        return await _call_runpod(prompt, settings, system_prompt)
    return await _call_ollama(prompt, settings, system_prompt)


async def _call_ollama(
    prompt: str,
    settings: Settings,
    system_prompt: str,
) -> str:
    """Appel via Ollama (local ou serveur dédié)."""
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


async def _call_runpod(
    prompt: str,
    settings: Settings,
    system_prompt: str,
) -> str:
    """Appel via RunPod Serverless (API OpenAI compatible vLLM)."""
    endpoint_url = (
        f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}"
        f"/openai/v1/chat/completions"
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            endpoint_url,
            headers={
                "Authorization": f"Bearer {settings.runpod_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "max_tokens": 4096,
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

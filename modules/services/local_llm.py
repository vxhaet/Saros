"""Service d'appel au LLM local (brique verte).

Supporte deux backends :
- Ollama (local ou serveur dédié)
- RunPod Serverless (GPU cloud EU, auto-shutdown)

Le backend est choisi automatiquement selon la configuration :
- Si SAROS_ANON_RUNPOD_API_KEY est défini → RunPod
- Sinon → Ollama
"""

import json

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
    """Appel via RunPod Serverless.

    RunPod Serverless fonctionne en 2 étapes :
    1. POST /run → lance le job, retourne un job_id
    2. GET /status/{job_id} → poll jusqu'à completion

    Ou en mode synchrone :
    POST /runsync → attend la réponse (timeout 30s par défaut, extensible)
    """
    endpoint_url = (
        f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}/runsync"
    )

    payload = {
        "input": {
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        # Lancer le job
        response = await client.post(
            endpoint_url,
            headers={
                "Authorization": f"Bearer {settings.runpod_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        # Mode synchrone : la réponse est directe
        if result.get("status") == "COMPLETED":
            return _extract_runpod_response(result)

        # Mode asynchrone : poll le statut
        job_id = result.get("id")
        if not job_id:
            raise ValueError(f"RunPod n'a pas retourné de job_id: {result}")

        status_url = (
            f"https://api.runpod.ai/v2/{settings.runpod_endpoint_id}/status/{job_id}"
        )

        import asyncio

        for _ in range(60):  # Max 5 minutes (60 * 5s)
            await asyncio.sleep(5)
            status_resp = await client.get(
                status_url,
                headers={"Authorization": f"Bearer {settings.runpod_api_key}"},
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()

            if status_data["status"] == "COMPLETED":
                return _extract_runpod_response(status_data)
            elif status_data["status"] in ("FAILED", "CANCELLED"):
                raise ValueError(
                    f"RunPod job échoué: {status_data.get('error', 'erreur inconnue')}"
                )

        raise TimeoutError("RunPod job timeout après 5 minutes.")


def _extract_runpod_response(result: dict) -> str:
    """Extrait le texte de la réponse RunPod."""
    output = result.get("output", {})

    # Format vLLM
    if isinstance(output, dict):
        choices = output.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        # Format texte direct
        if "text" in output:
            return output["text"]

    # Format brut
    if isinstance(output, str):
        return output

    return json.dumps(output)

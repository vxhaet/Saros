import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
import httpx

from .anonymizer import Anonymizer
from .config import settings
from .detector import detect_sensitive_entities, detect_sensitive_fields
from .llm_router import deanonymize, send_to_llm
from .file_handler import (
    extract_samples,
    extract_text_from_pdf,
    is_text_file,
    load_file,
    resolve_file_path,
)
from .models import (
    DeanonymizeRequest,
    DeanonymizeResponse,
    DetectionResponse,
    ExecutionRequest,
    ExecutionResponse,
    LlmSendRequest,
    LlmSendResponse,
    OrchestrationRequest,
)

app = FastAPI(title="Saros - Module Anonymisation", version="0.1.0")

# Stockage en mémoire des requêtes en attente de validation
_pending_requests: dict[str, dict] = {}


@app.post("/anonymisation/detect", response_model=DetectionResponse)
async def detect(request: OrchestrationRequest):
    """Analyse un fichier ou un message texte et détecte les données sensibles (RGPD).

    - Mode fichier : si des fichiers sont joints, analyse les colonnes du fichier.
    - Mode texte : si aucun fichier, analyse le message en langage naturel.

    Retourne la liste des données détectées avec une stratégie recommandée
    par le LLM local. L'utilisateur doit valider avant exécution.
    """
    try:
        if request.files and not is_text_file(request.files[0].name):
            return await _detect_file(request)
        if request.files and is_text_file(request.files[0].name):
            return await _detect_pdf(request)
        return await _detect_text(request)
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail="Le LLM local n'a pas répondu dans le délai imparti.",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Impossible de se connecter au LLM local (Ollama). Vérifiez qu'il est démarré.",
        )


async def _detect_file(request: OrchestrationRequest) -> DetectionResponse:
    file_info = request.files[0]

    try:
        file_path = resolve_file_path(
            settings.file_storage_path, file_info.fileId, file_info.name
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    df = load_file(file_path)
    samples = extract_samples(df)

    detected_fields = await detect_sensitive_fields(
        columns=list(df.columns),
        samples=samples,
        user_message=request.message,
        settings=settings,
    )

    _pending_requests[request.requestId] = {
        "mode": "file",
        "df": df,
        "file_info": file_info,
        "file_path": file_path,
    }

    return DetectionResponse(
        requestId=request.requestId,
        mode="file",
        detectedFields=detected_fields,
        totalRows=len(df),
        columns=list(df.columns),
    )


async def _detect_pdf(request: OrchestrationRequest) -> DetectionResponse:
    file_info = request.files[0]

    try:
        file_path = resolve_file_path(
            settings.file_storage_path, file_info.fileId, file_info.name
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    pdf_text = extract_text_from_pdf(file_path)
    if not pdf_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Le PDF ne contient pas de texte extractible.",
        )

    # Combiner le message utilisateur et le contenu du PDF pour la détection
    full_text = f"{request.message}\n\nContenu du document :\n{pdf_text}"

    detected_entities = await detect_sensitive_entities(
        user_message=full_text,
        settings=settings,
    )

    _pending_requests[request.requestId] = {
        "mode": "text",
        "message": pdf_text,
    }

    return DetectionResponse(
        requestId=request.requestId,
        mode="text",
        detectedEntities=detected_entities,
        originalMessage=pdf_text,
    )


async def _detect_text(request: OrchestrationRequest) -> DetectionResponse:
    detected_entities = await detect_sensitive_entities(
        user_message=request.message,
        settings=settings,
    )

    _pending_requests[request.requestId] = {
        "mode": "text",
        "message": request.message,
    }

    return DetectionResponse(
        requestId=request.requestId,
        mode="text",
        detectedEntities=detected_entities,
        originalMessage=request.message,
    )


@app.post("/anonymisation/execute", response_model=ExecutionResponse)
async def execute(request: ExecutionRequest):
    """Exécute l'anonymisation avec les données validées par l'utilisateur."""
    pending = _pending_requests.get(request.requestId)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Requête {request.requestId} introuvable. "
                "Lancez d'abord /anonymisation/detect."
            ),
        )

    mode = pending["mode"]
    del _pending_requests[request.requestId]

    if mode == "file":
        return _execute_file(request, pending)
    return _execute_text(request, pending)


def _execute_file(request: ExecutionRequest, pending: dict) -> ExecutionResponse:
    df = pending["df"]
    file_info = pending["file_info"]

    anonymizer = Anonymizer(encryption_key=settings.encryption_key)
    anonymized_df = anonymizer.anonymize(df, request.validatedFields)

    output_id = f"anon-{uuid.uuid4().hex[:12]}"
    output_dir = Path(settings.file_storage_path) / output_id
    output_dir.mkdir(parents=True, exist_ok=True)

    output_name = f"anonymized_{file_info.name}"
    output_path = str(output_dir / output_name)

    if file_info.name.endswith(".csv"):
        anonymized_df.to_csv(output_path, index=False)
    else:
        anonymized_df.to_excel(output_path, index=False)

    mappings_path = anonymizer.save_mappings(output_path)

    return ExecutionResponse(
        requestId=request.requestId,
        mode="file",
        anonymizedFileId=output_id,
        anonymizedFilePath=output_path,
        mappingFilePath=mappings_path,
        stats={
            "totalRows": len(anonymized_df),
            "fieldsAnonymized": len(request.validatedFields),
            "strategies": {
                "placeholder": sum(
                    1 for f in request.validatedFields if f.strategy == "placeholder"
                ),
                "encryption": sum(
                    1 for f in request.validatedFields if f.strategy == "encryption"
                ),
            },
        },
    )


def _execute_text(request: ExecutionRequest, pending: dict) -> ExecutionResponse:
    original_message = pending["message"]

    anonymizer = Anonymizer(encryption_key=settings.encryption_key)
    anonymized_message = anonymizer.anonymize_text(
        original_message, request.validatedEntities
    )

    return ExecutionResponse(
        requestId=request.requestId,
        mode="text",
        anonymizedMessage=anonymized_message,
        mappings=anonymizer.get_mappings(),
        stats={
            "entitiesAnonymized": len(request.validatedEntities),
            "strategies": {
                "placeholder": sum(
                    1 for e in request.validatedEntities if e.strategy == "placeholder"
                ),
                "encryption": sum(
                    1 for e in request.validatedEntities if e.strategy == "encryption"
                ),
            },
        },
    )


# ── Fonction 2 : Envoi LLM externe ──────────────────────────────────


@app.post("/llm/send", response_model=LlmSendResponse)
async def llm_send(request: LlmSendRequest):
    """Envoie du contenu à un LLM externe et retourne la réponse brute.

    Fonction indépendante, aucune connaissance de l'anonymisation.
    Peut être utilisée par n'importe quel module.
    """
    try:
        response = await send_to_llm(
            content=request.content,
            target_llm=request.targetLlm,
            settings=settings,
            system_prompt=request.systemPrompt,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail=f"Le LLM '{request.targetLlm}' n'a pas répondu dans le délai imparti.",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur du LLM '{request.targetLlm}' : {e.response.status_code} - {e.response.text}",
        )

    return LlmSendResponse(
        requestId=request.requestId,
        response=response,
        targetLlm=request.targetLlm,
    )


# ── Fonction 1 (suite) : Dé-anonymisation ───────────────────────────


@app.post("/anonymisation/deanonymize", response_model=DeanonymizeResponse)
async def deanonymize_endpoint(request: DeanonymizeRequest):
    """Dé-anonymise un texte en utilisant la table de mappings.

    Remplace les placeholders ([NOM_1], [EMAIL_1]...) par les valeurs originales
    et déchiffre les tokens Fernet si une clé est fournie.
    """
    result = deanonymize(request.text, request.mappings)

    return DeanonymizeResponse(
        requestId=request.requestId,
        deanonymizedText=result,
    )

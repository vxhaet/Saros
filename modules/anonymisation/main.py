import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
    DetectionResponse,
    ExecutionRequest,
    ExecutionResponse,
    OrchestrationRequest,
)
from .storage import (
    delete_pending_request,
    get_anonymisation_audit,
    get_conversation_mappings,
    get_pending_request,
    save_anonymisation_audit,
    save_conversation_mappings,
    save_pending_request,
)

app = FastAPI(title="Saros - Module Anonymisation", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoint 1 : Détection ──────────────────────────────────────────


@app.post("/anonymisation/detect", response_model=DetectionResponse)
async def detect(request: OrchestrationRequest):
    """Détecte les données sensibles dans un fichier ou un message texte.

    Retourne la liste des données détectées avec une stratégie recommandée.
    L'utilisateur doit valider avant d'appeler /anonymisation/execute.
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

    save_pending_request(request.requestId, {
        "mode": "file",
        "question": request.message,
        "conversationId": request.conversationId,
        "df": df,
        "file_info": {"fileId": file_info.fileId, "name": file_info.name, "mimeType": file_info.mimeType, "size": file_info.size},
        "file_path": file_path,
    })

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

    full_text = f"{request.message}\n\nContenu du document :\n{pdf_text}"

    detected_entities = await detect_sensitive_entities(
        user_message=full_text,
        settings=settings,
    )

    save_pending_request(request.requestId, {
        "mode": "text",
        "question": request.message,
        "content": pdf_text,
        "conversationId": request.conversationId,
    })

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

    save_pending_request(request.requestId, {
        "mode": "text",
        "question": request.message,
        "content": request.message,
        "conversationId": request.conversationId,
    })

    return DetectionResponse(
        requestId=request.requestId,
        mode="text",
        detectedEntities=detected_entities,
        originalMessage=request.message,
    )


# ── Endpoint 2 : Exécution complète ─────────────────────────────────


@app.post("/anonymisation/execute", response_model=ExecutionResponse)
async def execute(request: ExecutionRequest):
    """Anonymise, envoie au LLM externe, dé-anonymise et retourne la réponse finale.

    Tout se passe côté serveur. Les données anonymisées et les mappings
    ne sortent jamais du serveur. Le front reçoit uniquement la réponse
    finale dé-anonymisée.

    Les mappings sont persistés par conversationId pour garantir la cohérence
    au sein d'une discussion (même personne = même placeholder).
    """
    pending = get_pending_request(request.requestId)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Requête {request.requestId} introuvable. "
                "Lancez d'abord /anonymisation/detect."
            ),
        )

    delete_pending_request(request.requestId)

    mode = pending["mode"]

    if mode == "file":
        return await _execute_file(request, pending)
    return await _execute_text(request, pending)


async def _execute_file(
    request: ExecutionRequest, pending: dict
) -> ExecutionResponse:
    df = pending["df"]
    file_info = pending["file_info"]
    question = pending["question"]
    conv_id = request.conversationId

    # Charger les mappings existants de la conversation
    existing = get_conversation_mappings(conv_id)
    anonymizer = Anonymizer(
        encryption_key=settings.encryption_key,
        existing_mappings=existing,
    )

    # 1. Anonymiser le fichier
    anonymized_df = anonymizer.anonymize(df, request.validatedFields)

    output_id = f"anon-{uuid.uuid4().hex[:12]}"
    output_dir = Path(settings.file_storage_path) / output_id
    output_dir.mkdir(parents=True, exist_ok=True)

    file_name = file_info["name"] if isinstance(file_info, dict) else file_info.name
    output_name = f"anonymized_{file_name}"
    output_path = str(output_dir / output_name)

    if file_name.endswith(".csv"):
        anonymized_df.to_csv(output_path, index=False)
    else:
        anonymized_df.to_excel(output_path, index=False)

    anonymizer.save_mappings(output_path)

    # Sauvegarder les mappings de la conversation + audit
    mappings = anonymizer.get_mappings()
    save_conversation_mappings(conv_id, mappings)
    save_anonymisation_audit(conv_id, request.requestId, request.userId, mappings)

    # 2. Envoyer au LLM externe
    anonymized_content = f"{question}\n\nDonnées anonymisées :\n{anonymized_df.to_string(index=False)}"
    llm_response = await _call_llm(
        content=anonymized_content,
        target_llm=request.targetLlm,
        system_prompt=request.systemPrompt,
    )

    # 3. Dé-anonymiser la réponse
    final_response = deanonymize(llm_response, anonymizer.get_mappings())

    return ExecutionResponse(
        requestId=request.requestId,
        conversationId=conv_id,
        mode="file",
        response=final_response,
        anonymizedFileId=output_id,
        anonymizedFilePath=output_path,
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


async def _execute_text(
    request: ExecutionRequest, pending: dict
) -> ExecutionResponse:
    content = pending["content"]
    question = pending["question"]
    conv_id = request.conversationId

    # Charger les mappings existants de la conversation
    existing = get_conversation_mappings(conv_id)
    anonymizer = Anonymizer(
        encryption_key=settings.encryption_key,
        existing_mappings=existing,
    )

    # 1. Anonymiser le texte
    anonymized_message = anonymizer.anonymize_text(
        content, request.validatedEntities
    )

    # Sauvegarder les mappings de la conversation + audit
    mappings = anonymizer.get_mappings()
    save_conversation_mappings(conv_id, mappings)
    save_anonymisation_audit(conv_id, request.requestId, request.userId, mappings)

    # 2. Envoyer au LLM externe
    # Si la question et le contenu sont identiques (mode texte pur),
    # on envoie juste le message anonymisé.
    # Sinon (mode PDF), on combine la question + le contenu anonymisé.
    if question == content:
        llm_content = anonymized_message
    else:
        llm_content = f"{question}\n\n{anonymized_message}"

    llm_response = await _call_llm(
        content=llm_content,
        target_llm=request.targetLlm,
        system_prompt=request.systemPrompt,
    )

    # 3. Dé-anonymiser la réponse
    final_response = deanonymize(llm_response, anonymizer.get_mappings())

    return ExecutionResponse(
        requestId=request.requestId,
        conversationId=conv_id,
        mode="text",
        response=final_response,
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


async def _call_llm(
    content: str, target_llm: str, system_prompt: str | None = None
) -> str:
    """Appel interne au LLM externe. Jamais exposé au front."""
    try:
        return await send_to_llm(
            content=content,
            target_llm=target_llm,
            settings=settings,
            system_prompt=system_prompt,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail=f"Le LLM '{target_llm}' n'a pas répondu dans le délai imparti.",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur du LLM '{target_llm}' : {e.response.status_code} - {e.response.text}",
        )


# ── Endpoint de reporting ────────────────────────────────────────────


@app.get("/anonymisation/audit")
async def audit(
    conversation_id: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
):
    """Consulte le journal d'anonymisation pour le reporting réglementaire.

    Filtrable par conversation_id et/ou user_id.
    Retourne la liste des correspondances valeur originale ↔ valeur anonymisée.
    """
    records = get_anonymisation_audit(
        conversation_id=conversation_id,
        user_id=user_id,
        limit=limit,
    )

    # Convertir les datetime pour la sérialisation JSON
    for r in records:
        if "created_at" in r and hasattr(r["created_at"], "isoformat"):
            r["created_at"] = r["created_at"].isoformat()

    return {"total": len(records), "records": records}

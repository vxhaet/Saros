from pydantic import BaseModel
from enum import Enum


# --- Requête entrante (depuis l'orchestration) ---


class FileInfo(BaseModel):
    fileId: str
    name: str
    mimeType: str
    size: int


class RequestContext(BaseModel):
    application: str
    language: str = "fr"


class OrchestrationRequest(BaseModel):
    requestId: str
    userId: str
    conversationId: str
    message: str
    files: list[FileInfo] = []
    context: RequestContext


# --- Détection ---


class AnonymizationStrategy(str, Enum):
    PLACEHOLDER = "placeholder"
    ENCRYPTION = "encryption"


class DetectedField(BaseModel):
    field: str
    category: str
    rgpdArticle: str
    samples: list[str]
    recommendedStrategy: AnonymizationStrategy
    justification: str


class DetectedEntity(BaseModel):
    value: str
    category: str
    rgpdArticle: str
    recommendedStrategy: AnonymizationStrategy
    justification: str


class DetectionResponse(BaseModel):
    requestId: str
    status: str = "pending_validation"
    mode: str  # "file" ou "text"
    # Mode fichier
    detectedFields: list[DetectedField] = []
    totalRows: int = 0
    columns: list[str] = []
    # Mode texte
    detectedEntities: list[DetectedEntity] = []
    originalMessage: str | None = None


# --- Exécution (après validation utilisateur) ---


class FieldValidation(BaseModel):
    field: str
    category: str
    strategy: AnonymizationStrategy


class EntityValidation(BaseModel):
    value: str
    category: str
    strategy: AnonymizationStrategy


class ExecutionRequest(BaseModel):
    requestId: str
    userId: str
    # Mode fichier
    validatedFields: list[FieldValidation] = []
    # Mode texte
    validatedEntities: list[EntityValidation] = []


# --- Envoi LLM externe ---


class LlmSendRequest(BaseModel):
    requestId: str
    userId: str
    content: str
    targetLlm: str  # ex: "claude", "gpt-4o", "mistral-large"
    systemPrompt: str | None = None


class LlmSendResponse(BaseModel):
    requestId: str
    status: str = "completed"
    response: str
    targetLlm: str


class DeanonymizeRequest(BaseModel):
    requestId: str
    text: str
    mappings: dict


class DeanonymizeResponse(BaseModel):
    requestId: str
    status: str = "completed"
    deanonymizedText: str


class ExecutionResponse(BaseModel):
    requestId: str
    status: str = "completed"
    mode: str  # "file" ou "text"
    # Mode fichier
    anonymizedFileId: str | None = None
    anonymizedFilePath: str | None = None
    # Mode texte
    anonymizedMessage: str | None = None
    # Commun
    mappingFilePath: str | None = None
    mappings: dict | None = None
    stats: dict

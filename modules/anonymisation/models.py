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
    conversationId: str
    targetLlm: str  # ex: "claude-sonnet-4-6", "gpt-4o"
    systemPrompt: str | None = None
    webSearch: bool = True  # Active la recherche web via Tavily
    webSearchDomains: list[str] = []  # Restreint la recherche à ces domaines
    # Mode fichier
    validatedFields: list[FieldValidation] = []
    # Mode texte
    validatedEntities: list[EntityValidation] = []


class ExecutionResponse(BaseModel):
    requestId: str
    conversationId: str
    status: str = "completed"
    mode: str  # "file" ou "text"
    response: str  # Réponse finale dé-anonymisée
    webSearchUsed: bool = False
    # Mode fichier uniquement
    anonymizedFileId: str | None = None
    anonymizedFilePath: str | None = None
    stats: dict

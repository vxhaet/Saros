from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    file_storage_path: str = "/data/files"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b-instruct"
    encryption_key: str | None = None

    # MongoDB
    mongo_uri: str | None = None
    mongo_db_name: str = "saros"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_expiration_hours: int = 120

    # Recherche web
    tavily_api_key: str | None = None

    # LLM externes
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    model_config = {"env_prefix": "SAROS_ANON_"}


settings = Settings()

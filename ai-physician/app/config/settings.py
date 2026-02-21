"""Application configuration and settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service Configuration
    service_name: str = "ai-physician"
    ai_physician_port: int = 8005
    environment: str = "development"

    # MongoDB Configuration
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "ai_physician"
    mongodb_collection_sessions: str = "symptom_sessions"
    mongodb_collection_assessments: str = "triage_assessments"

    # GitHub Models API
    github_token: str
    github_models_endpoint: str = "https://models.inference.ai.azure.com"
    model_name: str = "Phi-4-mini-reasoning"
    model_temperature: float = 0.7
    model_max_tokens: int = 1000

    # JWT Configuration
    jwt_public_key_path: str = "../auth-service/src/main/resources/keys/public_key.pem"
    jwt_issuer: str = "medisecure-auth-service"
    jwt_algorithm: str = "RS256"

    # Cookie names (must match auth-service CookiesService)
    jwt_access_cookie_name: str = "access_token"
    jwt_refresh_cookie_name: str = "refresh_token"

    # Auth Service Integration
    auth_service_url: str = "http://localhost:8082"
    user_service_url: str = "http://localhost:8081"
    auth_verify_token_url: str = "http://localhost:8080/api/v1/auth/verify-token"

    # FHIR Server Configuration
    fhir_enabled: bool = False
    fhir_base_url: str = "http://hapi.fhir.org/baseR4"
    fhir_auth_token: Optional[str] = None
    fhir_use_mock: bool = True  # Use mock data as fallback

    # Google Maps API Configuration
    google_maps_api_key: Optional[str] = None
    provider_search_radius_m: int = 5000  # Default search radius in meters
    provider_search_max_results: int = 5  # Max providers to return

    # Safety Settings
    red_flag_keywords: str = (
        "chest pain,difficulty breathing,severe headache,suicidal,unconscious"
    )
    emergency_threshold_score: int = 8
    max_session_messages: int = 50

    # Streaming Configuration
    sse_retry_timeout: int = 30000
    sse_heartbeat_interval: int = 15

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False
        protected_namespaces = ("settings_",)


# Global settings instance
settings = Settings()

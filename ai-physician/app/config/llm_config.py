
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.config.settings import settings
from pydantic import SecretStr
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model name constants
# ---------------------------------------------------------------------------
_MODEL_SUPERVISOR = "meta/Meta-Llama-3.1-8B-Instruct"
_MODEL_INTERVIEW = "meta/Meta-Llama-3.1-8B-Instruct"
_MODEL_SCOUT = "meta/Meta-Llama-4-Scout-17B-16E-Instruct"  # Drug / Preventive / History
_MODEL_CLINICAL = "meta/Meta-Llama-3.1-8B-Instruct"  # Triage / Final Responder


# ---------------------------------------------------------------------------
# Internal factory
# ---------------------------------------------------------------------------
def _create_model(model_name: str, streaming: bool = True) -> BaseChatModel:
    """Instantiate a ChatOpenAI client pointed at the GitHub Models endpoint."""
    logger.info(
        f"Creating GitHub Models client: {model_name} (timeout: {settings.llm_request_timeout}s, streaming={streaming})"
    )
    return ChatOpenAI(
        base_url=settings.github_models_endpoint,
        api_key=SecretStr(settings.github_token),
        model=model_name,
        temperature=settings.model_temperature,
        extra_body={
            "max_tokens": settings.model_max_tokens,
            "top_p": 1.0,
            },
        streaming=streaming,
        timeout=settings.llm_request_timeout,
    )


# ---------------------------------------------------------------------------
# Per-agent public accessors
# ---------------------------------------------------------------------------
def get_supervisor_model() -> BaseChatModel:
    """Llama-3.1-8B-Instruct — Vaidya Supervisor: fast structured JSON routing. Non-streaming for JSON stability."""
    return _create_model(_MODEL_SUPERVISOR, streaming=False)


def get_interview_model() -> BaseChatModel:
    """Llama-3.1-8B-Instruct — Golden 4 Interview: ultra-fast conversational Q&A."""
    return _create_model(_MODEL_INTERVIEW, streaming=False)


def get_drug_model() -> BaseChatModel:
    """Llama-4-Scout-17B — Drug Interaction: strong clinical explanation + structured formatting."""
    return _create_model(_MODEL_SCOUT, streaming=False)


def get_preventive_model() -> BaseChatModel:
    """Llama-4-Scout-17B — Preventive/Chronic: guideline reasoning, care plans."""
    return _create_model(_MODEL_SCOUT, streaming=False)


def get_history_model() -> BaseChatModel:
    """Llama-4-Scout-17B — History Analysis: structured FHIR → narrative."""
    return _create_model(_MODEL_SCOUT, streaming=False)


def get_triage_model() -> BaseChatModel:
    """Llama-3.3-70B — Triage: 92.55% MedQA, safety-critical accuracy."""
    return _create_model(_MODEL_CLINICAL, streaming=False)


def get_final_model() -> BaseChatModel:
    """Llama-3.3-70B — Final Responder: clinically accurate, clearly worded patient output."""
    return _create_model(_MODEL_CLINICAL)

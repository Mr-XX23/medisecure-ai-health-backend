"""LLM configuration for GitHub Models API.

Per-agent model assignments (image spec):
  Vaidya Supervisor   → Phi-4 (14B)               — fast structured JSON routing
  Golden 4 Interview  → Phi-4-mini-instruct (3.8B) — ultra-fast conversational Q&A
  Drug Interaction    → Llama-4-Scout-17B           — strong clinical explanation
  Preventive/Chronic  → Llama-4-Scout-17B           — guideline reasoning, care plans
  History Analysis    → Llama-4-Scout-17B           — structured FHIR → narrative
  Triage              → Llama-3.3-70B               — 92.55% MedQA, safety-critical
  Final Responder     → Llama-3.3-70B               — clinically accurate patient output
"""

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.config.settings import settings
from typing import Optional
from pydantic import SecretStr
import asyncio
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model name constants
# ---------------------------------------------------------------------------
_MODEL_SUPERVISOR = "Phi-4"
_MODEL_INTERVIEW = "Phi-4-mini-instruct"
_MODEL_SCOUT = "Llama-4-Scout-17B-16E-Instruct"  # Drug / Preventive / History
_MODEL_CLINICAL = "Llama-3.3-70B-Instruct"  # Triage / Final Responder

# Legacy singleton (kept for any code that still calls get_chat_model directly)
_chat_model: Optional[BaseChatModel] = None
_chat_model_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Internal factory
# ---------------------------------------------------------------------------
def _create_model(model_name: str) -> BaseChatModel:
    """Instantiate a ChatOpenAI client pointed at the GitHub Models endpoint."""
    logger.info(f"Creating GitHub Models client: {model_name}")
    return ChatOpenAI(
        base_url=settings.github_models_endpoint,
        api_key=SecretStr(settings.github_token),
        model=model_name,
        temperature=settings.model_temperature,
        max_completion_tokens=settings.model_max_tokens,
        streaming=True,
    )


# ---------------------------------------------------------------------------
# Per-agent public accessors
# ---------------------------------------------------------------------------
def get_supervisor_model() -> BaseChatModel:
    """Phi-4 (14B) — Vaidya Supervisor: fast structured JSON routing."""
    return _create_model(_MODEL_SUPERVISOR)


def get_interview_model() -> BaseChatModel:
    """Phi-4-mini-instruct (3.8B) — Golden 4 Interview: ultra-fast conversational Q&A."""
    return _create_model(_MODEL_INTERVIEW)


def get_drug_model() -> BaseChatModel:
    """Llama-4-Scout-17B — Drug Interaction: strong clinical explanation + structured formatting."""
    return _create_model(_MODEL_SCOUT)


def get_preventive_model() -> BaseChatModel:
    """Llama-4-Scout-17B — Preventive/Chronic: guideline reasoning, care plans."""
    return _create_model(_MODEL_SCOUT)


def get_history_model() -> BaseChatModel:
    """Llama-4-Scout-17B — History Analysis: structured FHIR → narrative."""
    return _create_model(_MODEL_SCOUT)


def get_triage_model() -> BaseChatModel:
    """Llama-3.3-70B — Triage: 92.55% MedQA, safety-critical accuracy."""
    return _create_model(_MODEL_CLINICAL)


def get_final_model() -> BaseChatModel:
    """Llama-3.3-70B — Final Responder: clinically accurate, clearly worded patient output."""
    return _create_model(_MODEL_CLINICAL)


# ---------------------------------------------------------------------------
# Legacy helpers (backwards-compatible — routes to supervisor model)
# ---------------------------------------------------------------------------
def get_chat_model() -> BaseChatModel:
    """
    Legacy helper kept for backwards compatibility.

    New code should call the per-agent accessor (get_supervisor_model, etc.).
    Defaults to the supervisor model (Phi-4).
    """
    global _chat_model

    if _chat_model is not None:
        return _chat_model

    logger.info(
        f"Initializing legacy GitHub Models API client with model: {_MODEL_SUPERVISOR}"
    )
    _chat_model = _create_model(_MODEL_SUPERVISOR)
    logger.info(
        f"GitHub Models API client initialized (max_tokens={settings.model_max_tokens})"
    )
    return _chat_model


async def get_chat_model_async() -> BaseChatModel:
    """
    Async-safe version of get_chat_model using asyncio.Lock for concurrency protection.
    Use this when initializing in concurrent async contexts.
    """
    global _chat_model

    if _chat_model is not None:
        return _chat_model

    async with _chat_model_lock:
        if _chat_model is None:
            get_chat_model()

    return _chat_model  # type: ignore[return-value]

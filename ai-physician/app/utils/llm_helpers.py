"""Utility functions for LLM invocations with timeout handling."""

import asyncio
import logging
from typing import List, Any, Optional
from langchain_core.messages import BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from app.config.settings import settings

logger = logging.getLogger(__name__)


async def invoke_llm_with_timeout(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    timeout: Optional[float] = None,
    fallback_message: Optional[str] = None,
) -> Any:
    """
    Invoke an LLM with timeout protection.

    Args:
        llm: The language model to invoke
        messages: List of messages to send to the LLM
        timeout: Timeout in seconds (defaults to settings.llm_invoke_timeout)
        fallback_message: Message to return if timeout occurs (raises if None)

    Returns:
        LLM response

    Raises:
        asyncio.TimeoutError: If timeout occurs and no fallback_message provided
    """
    if timeout is None:
        timeout = settings.llm_invoke_timeout

    logger.info(f"📤 Invoking LLM with timeout: {timeout}s")

    try:
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout)
        logger.info("✅ LLM responded successfully")
        return response

    except asyncio.TimeoutError:
        logger.error(f"⏱️ LLM invocation timed out after {timeout}s")
        if fallback_message:
            logger.info(f"Using fallback message: {fallback_message[:100]}...")

            # Create a mock response object
            class FallbackResponse:
                def __init__(self, content: str):
                    self.content = content

            return FallbackResponse(fallback_message)
        raise

    except Exception as e:
        logger.error(f"❌ LLM invocation failed: {e}", exc_info=True)
        raise


async def stream_llm_with_timeout(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    timeout: Optional[float] = None,
):
    """
    Stream from an LLM with timeout protection.

    Args:
        llm: The language model to invoke
        messages: List of messages to send to the LLM
        timeout: Timeout in seconds (defaults to settings.llm_invoke_timeout)

    Yields:
        Chunks from the LLM stream

    Raises:
        asyncio.TimeoutError: If timeout occurs
    """
    if timeout is None:
        timeout = settings.llm_invoke_timeout

    logger.info(f"📤 Starting LLM stream with timeout: {timeout}s")

    try:

        async def _stream_with_timeout():
            """Wrapper coroutine that iterates the stream."""
            async for chunk in llm.astream(messages):
                yield chunk

        # Create a task for the stream and apply timeout
        stream = _stream_with_timeout()
        try:
            while True:
                chunk = await asyncio.wait_for(stream.__anext__(), timeout=timeout)
                yield chunk
        except StopAsyncIteration:
            logger.info("✅ LLM stream completed successfully")

    except asyncio.TimeoutError:
        logger.error(f"⏱️ LLM stream timed out after {timeout}s")
        raise

    except Exception as e:
        logger.error(f"❌ LLM stream failed: {e}", exc_info=True)
        raise

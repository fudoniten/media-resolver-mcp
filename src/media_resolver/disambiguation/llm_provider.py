"""LangChain LLM provider factory and configuration."""

import os
from typing import Any

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from media_resolver.config import LLMBackend

logger = structlog.get_logger()


class LLMProviderError(Exception):
    """Error creating or using LLM provider."""

    pass


def create_llm(config: LLMBackend) -> BaseChatModel:
    """
    Create LangChain chat model from backend configuration.

    Args:
        config: LLM backend configuration

    Returns:
        LangChain chat model instance

    Raises:
        LLMProviderError: If provider is not supported or configuration is invalid
    """
    log = logger.bind(component="llm_provider", provider=config.provider, model=config.model)

    provider = config.provider.lower()

    try:
        if provider == "anthropic":
            log.info("creating_anthropic_llm")
            # API key should be in environment or config
            api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise LLMProviderError(
                    "ANTHROPIC_API_KEY not found in environment or configuration"
                )

            return ChatAnthropic(
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                api_key=api_key,
            )

        elif provider == "openai":
            log.info("creating_openai_llm")
            api_key = config.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise LLMProviderError("OPENAI_API_KEY not found in environment or configuration")

            return ChatOpenAI(
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                api_key=api_key,
            )

        elif provider == "ollama":
            log.info("creating_ollama_llm", base_url=config.base_url)
            from langchain_community.chat_models import ChatOllama

            base_url = config.base_url or "http://localhost:11434"

            return ChatOllama(
                model=config.model,
                temperature=config.temperature,
                num_predict=config.max_tokens,
                base_url=base_url,
            )

        elif provider == "azure":
            log.info("creating_azure_openai_llm")
            from langchain_openai import AzureChatOpenAI

            # Azure requires additional env vars
            api_key = config.api_key or os.getenv("AZURE_OPENAI_API_KEY")
            endpoint = config.base_url or os.getenv("AZURE_OPENAI_ENDPOINT")
            deployment = config.model  # Azure uses deployment name

            if not api_key or not endpoint:
                raise LLMProviderError(
                    "Azure OpenAI requires AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT"
                )

            return AzureChatOpenAI(
                azure_deployment=deployment,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                api_key=api_key,
                azure_endpoint=endpoint,
            )

        elif provider == "cohere":
            log.info("creating_cohere_llm")
            from langchain_community.chat_models import ChatCohere

            api_key = config.api_key or os.getenv("COHERE_API_KEY")
            if not api_key:
                raise LLMProviderError("COHERE_API_KEY not found in environment or configuration")

            return ChatCohere(
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                cohere_api_key=api_key,
            )

        else:
            log.error("unsupported_provider", provider=provider)
            raise LLMProviderError(
                f"Unsupported LLM provider: {provider}. "
                f"Supported: anthropic, openai, ollama, azure, cohere"
            )

    except ImportError as e:
        log.error("llm_import_error", provider=provider, error=str(e))
        raise LLMProviderError(
            f"Failed to import {provider} provider. Install required package: {e}"
        ) from e
    except Exception as e:
        log.error("llm_creation_error", provider=provider, error=str(e))
        raise LLMProviderError(f"Failed to create {provider} LLM: {e}") from e


def get_model_info(config: LLMBackend) -> dict[str, Any]:
    """
    Get information about the configured model.

    Args:
        config: LLM backend configuration

    Returns:
        Dict with model information
    """
    return {
        "provider": config.provider,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "base_url": config.base_url if config.base_url else None,
    }

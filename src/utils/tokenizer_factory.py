# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Tokenizer factory for different LLM providers.
Provides unified interface for token counting and text truncation.
"""

import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List, Optional

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


class BaseTokenizer(ABC):
    """Base class for tokenizers."""

    @abstractmethod
    def encode(self, text: str) -> List[int]:
        """Encode text to token IDs."""
        pass

    @abstractmethod
    def decode(self, token_ids: List[int]) -> str:
        """Decode token IDs to text."""
        pass

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if not text:
            return 0
        return len(self.encode(text))

    def truncate_text(self, text: str, max_tokens: int) -> str:
        """Truncate text to max_tokens."""
        if not text:
            return text

        token_ids = self.encode(text)
        if len(token_ids) <= max_tokens:
            return text

        truncated_ids = token_ids[:max_tokens]
        return self.decode(truncated_ids)


class TiktokenTokenizer(BaseTokenizer):
    """Tokenizer for OpenAI models using tiktoken."""

    def __init__(self, model_name: str = "gpt-4"):
        """Initialize tiktoken tokenizer.

        Args:
            model_name: Model name to get the correct encoding
        """
        try:
            import tiktoken
        except ImportError:
            raise ImportError(
                "tiktoken is not installed. Please install it with: pip install tiktoken"
            )

        # Map model names to encodings
        # Most modern OpenAI models use cl100k_base
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            logger.warning(
                f"Model {model_name} not found in tiktoken, using cl100k_base encoding"
            )
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def encode(self, text: str) -> List[int]:
        """Encode text to token IDs."""
        return self.encoding.encode(text)

    def decode(self, token_ids: List[int]) -> str:
        """Decode token IDs to text."""
        return self.encoding.decode(token_ids)


class ApproximateTokenizer(BaseTokenizer):
    """Approximate tokenizer for models without native tokenizer support.

    Uses character-based estimation as fallback:
    - English (ASCII): ~4 characters per token
    - Non-English (e.g., Chinese): ~1.5 characters per token
    """

    def __init__(self):
        """Initialize approximate tokenizer."""
        self.chars_per_token_ascii = 4
        self.chars_per_token_unicode = 1.5

    def encode(self, text: str) -> List[int]:
        """Approximate encoding (returns character indices)."""
        # This is an approximation - we return character positions
        # to maintain interface compatibility
        return list(range(len(text)))

    def decode(self, token_ids: List[int]) -> str:
        """Not applicable for approximate tokenizer."""
        raise NotImplementedError(
            "Approximate tokenizer doesn't support decode operation"
        )

    def count_tokens(self, text: str) -> int:
        """Count tokens using character-based estimation."""
        if not text:
            return 0

        ascii_chars = 0
        unicode_chars = 0

        for char in text:
            if ord(char) < 128:
                ascii_chars += 1
            else:
                unicode_chars += 1

        # Calculate estimated tokens
        ascii_tokens = ascii_chars / self.chars_per_token_ascii
        unicode_tokens = unicode_chars / self.chars_per_token_unicode

        return int(ascii_tokens + unicode_tokens)

    def truncate_text(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens."""
        if not text:
            return text

        # Estimate character limit based on max_tokens
        # Use conservative estimate (average of ASCII and Unicode rates)
        avg_chars_per_token = (
            self.chars_per_token_ascii + self.chars_per_token_unicode
        ) / 2
        estimated_chars = int(max_tokens * avg_chars_per_token)

        if len(text) <= estimated_chars:
            return text

        # Truncate at character boundary
        return text[:estimated_chars]


class TokenizerFactory:
    """Factory for creating appropriate tokenizers based on model configuration."""

    _tokenizer_cache = {}

    @staticmethod
    @lru_cache(maxsize=10)
    def get_tokenizer(
        llm_type: Optional[str] = None, model_name: Optional[str] = None
    ) -> BaseTokenizer:
        """Get appropriate tokenizer for the given LLM configuration.

        Args:
            llm_type: Type of LLM (basic, reasoning, vision, code)
            model_name: Specific model name

        Returns:
            BaseTokenizer: Appropriate tokenizer instance
        """
        cache_key = f"{llm_type}_{model_name}"

        if cache_key in TokenizerFactory._tokenizer_cache:
            return TokenizerFactory._tokenizer_cache[cache_key]

        # Determine tokenizer based on model name or type
        tokenizer = None

        if model_name:
            model_lower = model_name.lower()

            # OpenAI models
            if any(
                x in model_lower
                for x in ["gpt", "openai", "o1", "o3", "text-embedding"]
            ):
                logger.info(f"Using tiktoken tokenizer for model: {model_name}")
                tokenizer = TiktokenTokenizer(model_name)

            # Azure OpenAI
            elif "azure" in model_lower:
                logger.info(f"Using tiktoken tokenizer for Azure model: {model_name}")
                # Azure uses OpenAI models, extract base model name
                base_model = "gpt-4"  # Default
                if "gpt-3.5" in model_lower:
                    base_model = "gpt-3.5-turbo"
                elif "gpt-4" in model_lower:
                    base_model = "gpt-4"
                tokenizer = TiktokenTokenizer(base_model)

            # DeepSeek models (compatible with OpenAI tokenizer)
            elif "deepseek" in model_lower:
                logger.info(f"Using tiktoken tokenizer for DeepSeek model: {model_name}")
                tokenizer = TiktokenTokenizer("gpt-4")

            # Google Gemini, Dashscope/Qwen, and other models
            # Use approximate tokenizer for now
            else:
                logger.info(
                    f"Using approximate tokenizer for model: {model_name} "
                    f"(native tokenizer not available)"
                )
                tokenizer = ApproximateTokenizer()
        else:
            # No model name provided, use approximate tokenizer
            logger.warning("No model name provided, using approximate tokenizer")
            tokenizer = ApproximateTokenizer()

        # Cache the tokenizer
        TokenizerFactory._tokenizer_cache[cache_key] = tokenizer
        return tokenizer

    @staticmethod
    def count_message_tokens(
        message: BaseMessage, tokenizer: Optional[BaseTokenizer] = None
    ) -> int:
        """Count tokens in a message.

        Args:
            message: Message to count tokens for
            tokenizer: Optional tokenizer to use (if None, creates default)

        Returns:
            int: Number of tokens in the message
        """
        if tokenizer is None:
            tokenizer = TokenizerFactory.get_tokenizer()

        total_tokens = 0

        # Count tokens in content
        if hasattr(message, "content") and message.content:
            if isinstance(message.content, str):
                total_tokens += tokenizer.count_tokens(message.content)

        # Count tokens in message type
        if hasattr(message, "type"):
            total_tokens += tokenizer.count_tokens(message.type)

        # Account for message structure overhead (roughly 4 tokens per message)
        total_tokens += 4

        # Count tokens in additional_kwargs
        if hasattr(message, "additional_kwargs") and message.additional_kwargs:
            # Estimate tokens for additional fields
            extra_str = str(message.additional_kwargs)
            total_tokens += tokenizer.count_tokens(extra_str)

        return max(1, total_tokens)

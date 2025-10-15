# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from src.utils.tokenizer_factory import (
    TokenizerFactory,
    TiktokenTokenizer,
    ApproximateTokenizer,
)


class TestTiktokenTokenizer:
    """Test cases for TiktokenTokenizer"""

    def test_encode_decode(self):
        """Test encoding and decoding with tiktoken"""
        tokenizer = TiktokenTokenizer("gpt-4")
        text = "Hello, how are you today?"

        # Encode and decode should be reversible
        token_ids = tokenizer.encode(text)
        decoded_text = tokenizer.decode(token_ids)

        assert isinstance(token_ids, list)
        assert len(token_ids) > 0
        assert decoded_text == text

    def test_count_tokens(self):
        """Test token counting"""
        tokenizer = TiktokenTokenizer("gpt-4")

        # Simple English text
        text = "Hello world"
        token_count = tokenizer.count_tokens(text)
        assert token_count > 0
        assert token_count < len(text)  # Should be less than character count

    def test_count_tokens_chinese(self):
        """Test token counting for Chinese text"""
        tokenizer = TiktokenTokenizer("gpt-4")

        # Chinese text
        text = "你好，世界！"
        token_count = tokenizer.count_tokens(text)
        assert token_count > 0

    def test_truncate_text(self):
        """Test text truncation at token boundaries"""
        tokenizer = TiktokenTokenizer("gpt-4")

        text = "This is a longer text that needs to be truncated at token boundaries."
        max_tokens = 5

        truncated = tokenizer.truncate_text(text, max_tokens)

        # Verify truncated text has correct token count
        assert tokenizer.count_tokens(truncated) <= max_tokens
        # Verify truncated text is a prefix of original text
        assert text.startswith(truncated) or len(truncated) < len(text)

    def test_empty_text(self):
        """Test handling of empty text"""
        tokenizer = TiktokenTokenizer("gpt-4")

        assert tokenizer.count_tokens("") == 0
        assert tokenizer.truncate_text("", 10) == ""


class TestApproximateTokenizer:
    """Test cases for ApproximateTokenizer"""

    def test_count_tokens_english(self):
        """Test approximate counting for English text"""
        tokenizer = ApproximateTokenizer()

        # 16 English characters should result in ~4 tokens
        text = "This is a test."  # 15 chars
        token_count = tokenizer.count_tokens(text)

        assert token_count > 0
        assert token_count <= len(text)

    def test_count_tokens_chinese(self):
        """Test approximate counting for Chinese text"""
        tokenizer = ApproximateTokenizer()

        # Chinese characters
        text = "这是一个测试"  # 6 characters
        token_count = tokenizer.count_tokens(text)

        # Should be around 6 * 1.5 = 4 tokens
        assert token_count >= 4
        assert token_count <= 6

    def test_count_tokens_mixed(self):
        """Test approximate counting for mixed language text"""
        tokenizer = ApproximateTokenizer()

        text = "Hello 你好 world 世界"
        token_count = tokenizer.count_tokens(text)

        assert token_count > 0

    def test_truncate_text(self):
        """Test approximate text truncation"""
        tokenizer = ApproximateTokenizer()

        text = "This is a longer text that needs to be truncated."
        max_tokens = 5

        truncated = tokenizer.truncate_text(text, max_tokens)

        # Verify truncated text is shorter
        assert len(truncated) <= len(text)

    def test_empty_text(self):
        """Test handling of empty text"""
        tokenizer = ApproximateTokenizer()

        assert tokenizer.count_tokens("") == 0
        assert tokenizer.truncate_text("", 10) == ""


class TestTokenizerFactory:
    """Test cases for TokenizerFactory"""

    def test_get_tokenizer_openai(self):
        """Test getting tokenizer for OpenAI models"""
        tokenizer = TokenizerFactory.get_tokenizer(model_name="gpt-4")
        assert isinstance(tokenizer, TiktokenTokenizer)

        tokenizer = TokenizerFactory.get_tokenizer(model_name="gpt-3.5-turbo")
        assert isinstance(tokenizer, TiktokenTokenizer)

    def test_get_tokenizer_deepseek(self):
        """Test getting tokenizer for DeepSeek models"""
        tokenizer = TokenizerFactory.get_tokenizer(model_name="deepseek-chat")
        assert isinstance(tokenizer, TiktokenTokenizer)

    def test_get_tokenizer_azure(self):
        """Test getting tokenizer for Azure models"""
        tokenizer = TokenizerFactory.get_tokenizer(model_name="azure-gpt-4")
        assert isinstance(tokenizer, TiktokenTokenizer)

    def test_get_tokenizer_gemini(self):
        """Test getting tokenizer for Google Gemini models"""
        tokenizer = TokenizerFactory.get_tokenizer(model_name="gemini-pro")
        assert isinstance(tokenizer, ApproximateTokenizer)

    def test_get_tokenizer_fallback(self):
        """Test fallback to approximate tokenizer for unknown models"""
        tokenizer = TokenizerFactory.get_tokenizer(model_name="unknown-model")
        assert isinstance(tokenizer, ApproximateTokenizer)

    def test_get_tokenizer_no_model(self):
        """Test getting tokenizer with no model name"""
        tokenizer = TokenizerFactory.get_tokenizer()
        assert isinstance(tokenizer, ApproximateTokenizer)

    def test_tokenizer_caching(self):
        """Test that tokenizers are cached"""
        tokenizer1 = TokenizerFactory.get_tokenizer(model_name="gpt-4")
        tokenizer2 = TokenizerFactory.get_tokenizer(model_name="gpt-4")

        # Should return the same instance (cached)
        assert tokenizer1 is tokenizer2

    def test_count_message_tokens_human(self):
        """Test counting tokens in HumanMessage"""
        message = HumanMessage(content="Hello, how are you?")
        token_count = TokenizerFactory.count_message_tokens(message)

        assert token_count > 0
        # Should include content + overhead
        assert token_count >= 4

    def test_count_message_tokens_ai(self):
        """Test counting tokens in AIMessage"""
        message = AIMessage(content="I'm doing well, thank you!")
        token_count = TokenizerFactory.count_message_tokens(message)

        assert token_count > 0

    def test_count_message_tokens_system(self):
        """Test counting tokens in SystemMessage"""
        message = SystemMessage(content="You are a helpful assistant.")
        token_count = TokenizerFactory.count_message_tokens(message)

        assert token_count > 0

    def test_count_message_tokens_with_additional_kwargs(self):
        """Test counting tokens with additional_kwargs"""
        message = ToolMessage(
            content="Tool result",
            tool_call_id="test",
            additional_kwargs={"extra": "data", "more": "information"},
        )
        token_count = TokenizerFactory.count_message_tokens(message)

        assert token_count > 0

    def test_count_message_tokens_empty(self):
        """Test counting tokens in message with empty content"""
        message = HumanMessage(content="")
        token_count = TokenizerFactory.count_message_tokens(message)

        # Should have at least 1 token for message overhead
        assert token_count >= 1

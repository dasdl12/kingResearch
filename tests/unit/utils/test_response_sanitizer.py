# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Unit tests for response_sanitizer module.
"""

import pytest
from src.utils.response_sanitizer import (
    sanitize_llm_response,
    create_error_placeholder,
    _remove_special_tokens,
    _detect_repetitive_pattern,
    _validate_content_structure,
)


class TestRemoveSpecialTokens:
    """Test special token removal."""

    def test_remove_end_of_sentence_token(self):
        """Test removal of end_of_sentence token."""
        content = "Hello <|end▁of▁sentence|> World"
        result = _remove_special_tokens(content)
        assert result == "Hello  World"

    def test_remove_multiple_special_tokens(self):
        """Test removal of multiple special tokens."""
        content = "<|begin▁of▁text|>Hello<|end▁of▁sentence|>"
        result = _remove_special_tokens(content)
        assert result == "Hello"

    def test_no_special_tokens(self):
        """Test content without special tokens."""
        content = "Normal text without any special tokens"
        result = _remove_special_tokens(content)
        assert result == content


class TestDetectRepetitivePattern:
    """Test repetitive pattern detection."""

    def test_detect_number_repetition(self):
        """Test detection of excessive number repetition."""
        content = "6.2.2.1.2.2.2.2.2.2.2.2.2.2.2.2.2.2"
        result = _detect_repetitive_pattern(content)
        assert result["has_issue"] is True
        assert "number repetition" in result["pattern"].lower()

    def test_detect_character_repetition(self):
        """Test detection of excessive character repetition."""
        content = "aaaaaaaaaaaaaaaaaaaaaaaaa normal text"
        result = _detect_repetitive_pattern(content)
        assert result["has_issue"] is True
        assert "character repetition" in result["pattern"].lower()

    def test_detect_word_repetition(self):
        """Test detection of excessive word repetition."""
        content = "test test test test test test test test test test test test"
        result = _detect_repetitive_pattern(content)
        assert result["has_issue"] is True
        assert "word repetition" in result["pattern"].lower()

    def test_normal_content(self):
        """Test normal content without excessive repetition."""
        content = "This is a normal sentence with proper structure and no repetition."
        result = _detect_repetitive_pattern(content)
        assert result["has_issue"] is False
        assert result["pattern"] is None


class TestValidateContentStructure:
    """Test content structure validation."""

    def test_empty_content(self):
        """Test validation of empty content."""
        result = _validate_content_structure("")
        assert result["is_valid"] is False
        assert "empty" in result["reason"].lower()

    def test_too_short_content(self):
        """Test validation of too short content."""
        result = _validate_content_structure("Hi")
        assert result["is_valid"] is False
        assert "too short" in result["reason"].lower()

    def test_normal_content(self):
        """Test validation of normal content."""
        content = "This is a proper research finding with sufficient length and meaningful content."
        result = _validate_content_structure(content)
        assert result["is_valid"] is True
        assert result["reason"] is None

    def test_excessive_special_characters(self):
        """Test validation of content with too many special characters."""
        content = "!@#$%^&*()_+{}|:<>?!@#$%^&*()_+{}|:<>?!@#$%^&*()_+{}|:<>?"
        result = _validate_content_structure(content)
        assert result["is_valid"] is False
        assert "non-text characters" in result["reason"].lower()


class TestSanitizeLLMResponse:
    """Test the main sanitization function."""

    def test_sanitize_valid_content(self):
        """Test sanitization of valid content."""
        content = "This is a valid research finding with proper structure and content."
        result = sanitize_llm_response(content, "Test Step")
        assert result["is_valid"] is True
        assert result["content"] == content
        assert result["was_modified"] is False
        assert result["issue"] is None

    def test_sanitize_content_with_special_tokens(self):
        """Test sanitization of content with special tokens."""
        content = "Research finding <|end▁of▁sentence|> with special tokens in the middle."
        result = sanitize_llm_response(content, "Test Step")
        assert result["is_valid"] is True
        assert "<|end▁of▁sentence|>" not in result["content"]
        assert result["was_modified"] is True

    def test_sanitize_repetitive_content(self):
        """Test sanitization of content with repetitive patterns."""
        content = "6.2.2.1.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2.2"
        result = sanitize_llm_response(content, "Test Step")
        assert result["is_valid"] is False
        assert "repetitive pattern" in result["issue"].lower()

    def test_sanitize_empty_content(self):
        """Test sanitization of empty content."""
        result = sanitize_llm_response("", "Test Step")
        assert result["is_valid"] is False
        assert "empty" in result["issue"].lower() or "too short" in result["issue"].lower()

    def test_sanitize_non_string_content(self):
        """Test sanitization of non-string content."""
        result = sanitize_llm_response(None, "Test Step")
        assert result["is_valid"] is False
        assert "invalid content type" in result["issue"].lower()


class TestCreateErrorPlaceholder:
    """Test error placeholder creation."""

    def test_create_error_placeholder(self):
        """Test error placeholder creation."""
        placeholder = create_error_placeholder("Test Step", "Invalid content")
        assert "Test Step" in placeholder
        assert "Invalid content" in placeholder
        assert "Error" in placeholder
        assert "LLM response" in placeholder

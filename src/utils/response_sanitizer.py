# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Response sanitizer for cleaning LLM outputs.
Filters special tokens, detects anomalies, and validates content.
"""

import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Special tokens that should be filtered from LLM responses
SPECIAL_TOKENS = [
    r"<\|end▁of▁sentence\|>",
    r"<\|begin▁of▁text\|>",
    r"<\|end▁of▁text\|>",
    r"<\|start▁header▁id\|>",
    r"<\|end▁header▁id\|>",
    r"<\|eot_id\|>",
    r"<\|start_header_id\|>",
    r"<\|end_header_id\|>",
]

# Maximum length for reasonable content (to prevent memory issues)
MAX_CONTENT_LENGTH = 500000  # 500KB of text

# Minimum meaningful content length
MIN_CONTENT_LENGTH = 10


def _remove_special_tokens(content: str) -> str:
    """Remove special tokens from content."""
    cleaned = content
    for token_pattern in SPECIAL_TOKENS:
        cleaned = re.sub(token_pattern, "", cleaned)
    return cleaned


def _detect_repetitive_pattern(content: str, max_check_length: int = 1000) -> Dict[str, Any]:
    """
    Detect if content contains excessive repetitive patterns.

    Returns:
        dict with 'has_issue' (bool) and 'pattern' (str) if detected
    """
    # Check only the first part to avoid performance issues
    check_text = content[:max_check_length]

    # Pattern 1: Excessive number repetition like "6.2.2.1.2.2.2.2.2..."
    number_pattern = re.findall(r"(\d+\.){10,}", check_text)
    if number_pattern:
        return {
            "has_issue": True,
            "pattern": f"Excessive number repetition: {number_pattern[0][:50]}...",
        }

    # Pattern 2: Character/word repetition (e.g., "aaaaaa..." or "word word word...")
    char_repeat = re.search(r"(.)\1{20,}", check_text)
    if char_repeat:
        return {
            "has_issue": True,
            "pattern": f"Excessive character repetition: '{char_repeat.group(0)[:20]}...'",
        }

    # Pattern 3: Word repetition
    word_repeat = re.search(r"\b(\w+)(\s+\1){10,}", check_text)
    if word_repeat:
        return {
            "has_issue": True,
            "pattern": f"Excessive word repetition: '{word_repeat.group(0)[:50]}...'",
        }

    return {"has_issue": False, "pattern": None}


def _validate_content_structure(content: str) -> Dict[str, Any]:
    """
    Validate that content has meaningful structure.

    Returns:
        dict with 'is_valid' (bool) and 'reason' (str) if invalid
    """
    if not content or not content.strip():
        return {"is_valid": False, "reason": "Empty content"}

    if len(content) < MIN_CONTENT_LENGTH:
        return {"is_valid": False, "reason": f"Content too short (< {MIN_CONTENT_LENGTH} chars)"}

    if len(content) > MAX_CONTENT_LENGTH:
        logger.warning(f"Content exceeds {MAX_CONTENT_LENGTH} characters, truncating")
        return {
            "is_valid": True,
            "reason": "Content truncated due to excessive length",
            "truncated": True,
        }

    # Check if content is mostly whitespace or special characters
    text_chars = sum(c.isalnum() or c.isspace() for c in content)
    if text_chars / len(content) < 0.5:
        return {
            "is_valid": False,
            "reason": "Content contains too many non-text characters",
        }

    return {"is_valid": True, "reason": None}


def sanitize_llm_response(content: str, step_title: str = "unknown") -> Dict[str, Any]:
    """
    Sanitize LLM response by filtering special tokens, detecting anomalies,
    and validating content structure.

    Args:
        content: Raw LLM response content
        step_title: Title of the current step (for logging)

    Returns:
        dict with:
            - 'content': Cleaned content (str)
            - 'is_valid': Whether content passed validation (bool)
            - 'issue': Description of any issues found (str or None)
            - 'was_modified': Whether content was modified (bool)
    """
    if not isinstance(content, str):
        logger.error(f"[{step_title}] Non-string content received: {type(content)}")
        return {
            "content": "",
            "is_valid": False,
            "issue": f"Invalid content type: {type(content)}",
            "was_modified": False,
        }

    original_content = content
    was_modified = False

    # Step 1: Remove special tokens
    cleaned_content = _remove_special_tokens(content)
    if cleaned_content != original_content:
        was_modified = True
        removed_tokens = len(original_content) - len(cleaned_content)
        logger.warning(
            f"[{step_title}] Removed special tokens from LLM response "
            f"({removed_tokens} characters filtered)"
        )

    # Step 2: Detect repetitive patterns
    repetition_check = _detect_repetitive_pattern(cleaned_content)
    if repetition_check["has_issue"]:
        logger.error(
            f"[{step_title}] Detected anomalous repetitive pattern: "
            f"{repetition_check['pattern']}"
        )
        return {
            "content": cleaned_content,
            "is_valid": False,
            "issue": f"Repetitive pattern detected: {repetition_check['pattern']}",
            "was_modified": was_modified,
        }

    # Step 3: Validate content structure
    validation = _validate_content_structure(cleaned_content)
    if not validation["is_valid"]:
        logger.error(
            f"[{step_title}] Content validation failed: {validation['reason']}"
        )
        return {
            "content": cleaned_content,
            "is_valid": False,
            "issue": validation["reason"],
            "was_modified": was_modified,
        }

    # Step 4: Handle truncation if needed
    if validation.get("truncated"):
        cleaned_content = cleaned_content[:MAX_CONTENT_LENGTH]
        was_modified = True

    # Success
    if was_modified:
        logger.info(f"[{step_title}] LLM response sanitized successfully")

    return {
        "content": cleaned_content,
        "is_valid": True,
        "issue": None,
        "was_modified": was_modified,
    }


def create_error_placeholder(step_title: str, issue: str) -> str:
    """
    Create a placeholder message for invalid LLM responses.

    Args:
        step_title: Title of the step that failed
        issue: Description of the issue

    Returns:
        Formatted error message
    """
    return f"""# Error in Step Execution

**Step**: {step_title}

**Issue**: The LLM response contained invalid or corrupted content.

**Technical Details**: {issue}

**Status**: This step could not be completed due to model output anomalies.
The research will continue with remaining steps.
"""

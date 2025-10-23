# src/utils/token_manager.py
import copy
import json
import logging
import re
from typing import List, Optional
from functools import lru_cache

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.config import load_yaml_config

logger = logging.getLogger(__name__)

# Try to import tiktoken, fallback gracefully if not available
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
    logger.info("tiktoken loaded successfully for accurate token counting")
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available, falling back to character-based estimation")


def get_search_config():
    config = load_yaml_config("conf.yaml")
    search_config = config.get("MODEL_TOKEN_LIMITS", {})
    return search_config


class ContextManager:
    """Enhanced context manager with tiktoken support and intelligent compression"""

    def __init__(
        self,
        token_limit: int,
        preserve_prefix_message_count: int = 0,
        enable_smart_summary: bool = True,
        sliding_window_size: int = 5
    ):
        """
        Initialize ContextManager

        Args:
            token_limit: Maximum token limit
            preserve_prefix_message_count: Number of messages to preserve at the beginning
            enable_smart_summary: Enable intelligent summarization of old messages
            sliding_window_size: Number of recent messages to keep in full
        """
        self.token_limit = token_limit
        self.preserve_prefix_message_count = preserve_prefix_message_count
        self.enable_smart_summary = enable_smart_summary
        self.sliding_window_size = sliding_window_size

        # Initialize tiktoken encoding
        self._encoding = self._init_tiktoken_encoding()

    @lru_cache(maxsize=1)
    def _init_tiktoken_encoding(self):
        """Initialize tiktoken encoding with caching"""
        if not TIKTOKEN_AVAILABLE:
            return None

        try:
            # Try o200k_base first (supports GPT-5, GPT-4o, etc.)
            encoding = tiktoken.get_encoding("o200k_base")
            logger.info("Using o200k_base encoding (supports GPT-5-Nano)")
            return encoding
        except Exception:
            try:
                # Fallback to cl100k_base (supports GPT-4, GPT-3.5-turbo)
                encoding = tiktoken.get_encoding("cl100k_base")
                logger.info("Using cl100k_base encoding (fallback)")
                return encoding
            except Exception as e:
                logger.warning(f"Failed to initialize tiktoken encoding: {e}")
                return None

    def count_tokens(self, messages: List[BaseMessage]) -> int:
        """
        Count tokens in message list

        Args:
            messages: List of messages

        Returns:
            Number of tokens
        """
        total_tokens = 0
        for message in messages:
            total_tokens += self._count_message_tokens(message)
        return total_tokens

    def _count_message_tokens(self, message: BaseMessage) -> int:
        """
        Count tokens in a single message with enhanced accuracy

        Args:
            message: Message object

        Returns:
            Number of tokens
        """
        token_count = 0

        # Count tokens in content field
        if hasattr(message, "content") and message.content:
            if isinstance(message.content, str):
                token_count += self._count_text_tokens(message.content)

        # Count role-related tokens
        if hasattr(message, "type"):
            token_count += self._count_text_tokens(message.type)

        # Enhanced handling for different message types with realistic multipliers
        if isinstance(message, SystemMessage):
            # System messages are important but usually short
            token_count = int(token_count * 1.05)
        elif isinstance(message, HumanMessage):
            # Human messages use normal estimation
            pass
        elif isinstance(message, AIMessage):
            # AI messages may contain reasoning content and tool calls
            token_count = int(token_count * 1.15)

            # Handle tool calls in additional_kwargs
            if hasattr(message, "tool_calls") and message.tool_calls:
                # More accurate estimation for tool calls
                for tool_call in message.tool_calls:
                    token_count += self._count_text_tokens(str(tool_call))

        elif isinstance(message, ToolMessage):
            # Tool messages often contain structured data
            token_count = int(token_count * 1.2)

        # Process additional information in additional_kwargs
        if hasattr(message, "additional_kwargs") and message.additional_kwargs:
            extra_str = str(message.additional_kwargs)
            token_count += self._count_text_tokens(extra_str)

        # Ensure at least 1 token
        return max(1, token_count)

    def _count_text_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken if available, otherwise fallback to estimation

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if not text:
            return 0

        # Use tiktoken if available (much more accurate)
        if TIKTOKEN_AVAILABLE and self._encoding is not None:
            try:
                return len(self._encoding.encode(text, disallowed_special=()))
            except Exception as e:
                logger.warning(f"tiktoken encoding failed, falling back to estimation: {e}")
                # Fall through to character-based estimation

        # Fallback: character-based estimation
        return self._estimate_tokens_by_chars(text)

    def _estimate_tokens_by_chars(self, text: str) -> int:
        """
        Estimate tokens based on character count (fallback method)

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated number of tokens
        """
        if not text:
            return 0

        english_chars = 0
        non_english_chars = 0

        for char in text:
            # Check if character is ASCII (English letters, digits, punctuation)
            if ord(char) < 128:
                english_chars += 1
            else:
                non_english_chars += 1

        # Calculate tokens: English at 4 chars/token, others at 1 char/token
        english_tokens = english_chars // 4
        non_english_tokens = non_english_chars

        return english_tokens + non_english_tokens

    def is_over_limit(self, messages: List[BaseMessage]) -> bool:
        """
        Check if messages exceed token limit

        Args:
            messages: List of messages

        Returns:
            Whether limit is exceeded
        """
        return self.count_tokens(messages) > self.token_limit

    def compress_messages(self, state: dict) -> dict:
        """
        Compress messages to fit within token limit with intelligent strategies

        Args:
            state: state with original messages

        Returns:
            Compressed state with compressed messages
        """
        # If not set token_limit, return original state
        if self.token_limit is None:
            logger.info("No token_limit set, the context management doesn't work.")
            return state

        if not isinstance(state, dict) or "messages" not in state:
            logger.warning("No messages found in state")
            return state

        messages = state["messages"]

        if not self.is_over_limit(messages):
            return state

        # Apply intelligent compression
        compressed_messages = self._intelligent_compress(messages)

        original_tokens = self.count_tokens(messages)
        compressed_tokens = self.count_tokens(compressed_messages)

        logger.info(
            f"Message compression completed: {original_tokens} -> {compressed_tokens} tokens "
            f"(reduction: {((original_tokens - compressed_tokens) / original_tokens * 100):.1f}%)"
        )

        state["messages"] = compressed_messages
        return state

    def _intelligent_compress(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Intelligent compression with multiple strategies

        Strategies:
        1. Preserve system messages and recent messages (sliding window)
        2. Summarize or truncate old ToolMessages and long content
        3. Keep important structural messages

        Args:
            messages: List of messages to compress

        Returns:
            Compressed message list
        """
        if not messages:
            return messages

        available_tokens = self.token_limit
        result_messages = []

        # Strategy 1: Preserve prefix messages (system prompts, initial context)
        prefix_count = min(self.preserve_prefix_message_count, len(messages))
        for i in range(prefix_count):
            msg = messages[i]
            msg_tokens = self._count_message_tokens(msg)

            if available_tokens >= msg_tokens:
                result_messages.append(msg)
                available_tokens -= msg_tokens
            elif available_tokens > 0:
                # Truncate if needed
                truncated_msg = self._truncate_message_content(msg, available_tokens)
                result_messages.append(truncated_msg)
                return result_messages  # No more space
            else:
                break

        # Strategy 2: Process remaining messages with sliding window
        remaining_messages = messages[prefix_count:]

        if not remaining_messages:
            return result_messages

        # Reserve space for recent messages (sliding window)
        recent_messages = remaining_messages[-self.sliding_window_size:]
        older_messages = remaining_messages[:-self.sliding_window_size] if len(remaining_messages) > self.sliding_window_size else []

        # Calculate tokens needed for recent messages
        recent_tokens_needed = sum(self._count_message_tokens(msg) for msg in recent_messages)

        # Allocate tokens: 60% for older messages, 40% for recent messages
        older_budget = int(available_tokens * 0.6)
        recent_budget = available_tokens - older_budget

        # Process older messages with summarization
        if older_messages and older_budget > 0:
            compressed_older = self._compress_older_messages(older_messages, older_budget)
            result_messages.extend(compressed_older)
            available_tokens -= sum(self._count_message_tokens(msg) for msg in compressed_older)

        # Add recent messages (sliding window)
        for msg in recent_messages:
            msg_tokens = self._count_message_tokens(msg)

            if available_tokens >= msg_tokens:
                result_messages.append(msg)
                available_tokens -= msg_tokens
            elif available_tokens > 0:
                # Truncate if space is limited
                truncated_msg = self._truncate_message_content(msg, available_tokens)
                result_messages.append(truncated_msg)
                break
            else:
                # No more space
                break

        return result_messages

    def _compress_older_messages(
        self,
        messages: List[BaseMessage],
        token_budget: int
    ) -> List[BaseMessage]:
        """
        Compress older messages with intelligent summarization

        Args:
            messages: Older messages to compress
            token_budget: Token budget for these messages

        Returns:
            Compressed older messages
        """
        if not messages or token_budget <= 0:
            return []

        compressed = []
        remaining_budget = token_budget

        for msg in reversed(messages):  # Process from newest to oldest
            msg_tokens = self._count_message_tokens(msg)

            # For ToolMessages and very long messages, apply aggressive compression
            if isinstance(msg, ToolMessage) or msg_tokens > 1000:
                if self.enable_smart_summary:
                    summarized_msg = self._summarize_message(msg, max_tokens=min(300, remaining_budget))
                    summarized_tokens = self._count_message_tokens(summarized_msg)

                    if remaining_budget >= summarized_tokens:
                        compressed.insert(0, summarized_msg)
                        remaining_budget -= summarized_tokens
                else:
                    # Truncate instead of summarize
                    if remaining_budget > 0:
                        truncated_msg = self._truncate_message_content(msg, min(msg_tokens // 3, remaining_budget))
                        compressed.insert(0, truncated_msg)
                        remaining_budget -= self._count_message_tokens(truncated_msg)
            else:
                # Keep shorter messages if budget allows
                if remaining_budget >= msg_tokens:
                    compressed.insert(0, msg)
                    remaining_budget -= msg_tokens
                elif remaining_budget > 0:
                    truncated_msg = self._truncate_message_content(msg, remaining_budget)
                    compressed.insert(0, truncated_msg)
                    remaining_budget = 0

            if remaining_budget <= 0:
                break

        return compressed

    def _summarize_message(self, message: BaseMessage, max_tokens: int = 300) -> BaseMessage:
        """
        Create a summarized version of a message (rule-based summarization)

        Args:
            message: Message to summarize
            max_tokens: Maximum tokens for summary

        Returns:
            Summarized message
        """
        summarized_msg = copy.deepcopy(message)

        if not message.content or not isinstance(message.content, str):
            return summarized_msg

        content = message.content

        # Check if content is JSON - if so, use smart JSON compression
        json_compressed = self._try_compress_json(content, max_tokens)
        if json_compressed is not None:
            summarized_msg.content = json_compressed
            return summarized_msg

        # Strategy: Extract key information patterns
        summary_parts = []

        # Extract findings in <finding> tags
        findings = re.findall(r'<finding>(.*?)</finding>', content, re.DOTALL)
        if findings:
            # Keep first and last finding, summarize middle ones
            if len(findings) <= 2:
                summary_parts.extend(findings)
            else:
                summary_parts.append(findings[0][:500])  # First finding (truncated)
                summary_parts.append(f"[... {len(findings) - 2} findings omitted ...]")
                summary_parts.append(findings[-1][:500])  # Last finding (truncated)
        else:
            # No findings tags, extract key sentences
            sentences = re.split(r'[.!?]\s+', content)

            # Keep first 2 and last 2 sentences
            if len(sentences) <= 4:
                summary_parts.extend(sentences)
            else:
                summary_parts.extend(sentences[:2])
                summary_parts.append(f"[... {len(sentences) - 4} sentences omitted ...]")
                summary_parts.extend(sentences[-2:])

        # Combine summary
        summary_content = " ".join(summary_parts)

        # Truncate to max_tokens
        estimated_tokens = self._count_text_tokens(summary_content)
        if estimated_tokens > max_tokens:
            # Rough truncation based on character ratio
            char_limit = int(len(summary_content) * (max_tokens / estimated_tokens))
            summary_content = summary_content[:char_limit] + "... [truncated]"

        # Add summary marker
        summarized_msg.content = f"[SUMMARIZED] {summary_content}"

        return summarized_msg

    def _truncate_message_content(
        self, message: BaseMessage, max_tokens: int
    ) -> BaseMessage:
        """
        Truncate message content while preserving structure

        Args:
            message: The message to truncate
            max_tokens: Maximum number of tokens to keep

        Returns:
            New message instance with truncated content
        """
        # Create a deep copy of the original message to preserve all attributes
        truncated_message = copy.deepcopy(message)

        if not message.content or not isinstance(message.content, str):
            return truncated_message

        # Check if content is JSON - if so, use smart JSON compression
        json_compressed = self._try_compress_json(message.content, max_tokens)
        if json_compressed is not None:
            truncated_message.content = json_compressed
            return truncated_message

        # Estimate character limit based on token limit
        # Use conservative ratio: assume 2 chars per token for safety
        char_limit = max_tokens * 2

        # Truncate content
        if len(message.content) > char_limit:
            truncated_message.content = message.content[:char_limit] + "... [truncated]"
        else:
            truncated_message.content = message.content

        return truncated_message

    def _try_compress_json(self, content: str, max_tokens: int) -> Optional[str]:
        """
        Try to compress JSON content intelligently while preserving structure

        Args:
            content: Content to compress
            max_tokens: Maximum tokens for compressed content

        Returns:
            Compressed JSON string if content is valid JSON, None otherwise
        """
        try:
            # Try to parse as JSON
            data = json.loads(content.strip())
        except (json.JSONDecodeError, ValueError):
            # Not valid JSON, return None to use regular compression
            return None

        # Compress based on data type
        if isinstance(data, list):
            return self._compress_json_array(data, max_tokens)
        elif isinstance(data, dict):
            return self._compress_json_object(data, max_tokens)
        else:
            # Simple value, keep as is
            return json.dumps(data, ensure_ascii=False)

    def _compress_json_array(self, array: list, max_tokens: int) -> str:
        """
        Compress JSON array by keeping first and last elements

        Args:
            array: JSON array to compress
            max_tokens: Maximum tokens for compressed content

        Returns:
            Compressed JSON array as string
        """
        if not array:
            return "[]"

        # Calculate how many elements we can keep
        # Start with all elements and remove middle ones if needed
        compressed_array = array.copy()
        
        while len(compressed_array) > 2:
            # Try current array
            current_json = json.dumps(compressed_array, ensure_ascii=False)
            tokens = self._count_text_tokens(current_json)
            
            if tokens <= max_tokens:
                break
            
            # Remove middle element(s)
            if len(compressed_array) <= 4:
                # Keep first 2 and last 1
                compressed_array = compressed_array[:2] + compressed_array[-1:]
            else:
                # Keep first 2 and last 2, remove middle
                mid = len(compressed_array) // 2
                compressed_array.pop(mid)

        # Final check - if still too large, keep only first and last
        current_json = json.dumps(compressed_array, ensure_ascii=False)
        if self._count_text_tokens(current_json) > max_tokens and len(compressed_array) > 2:
            compressed_array = [compressed_array[0], compressed_array[-1]]

        return json.dumps(compressed_array, ensure_ascii=False)

    def _compress_json_object(self, obj: dict, max_tokens: int) -> str:
        """
        Compress JSON object by keeping important fields

        Args:
            obj: JSON object to compress
            max_tokens: Maximum tokens for compressed content

        Returns:
            Compressed JSON object as string
        """
        if not obj:
            return "{}"

        # Priority fields to keep (common important fields)
        priority_fields = ['url', 'title', 'type', 'score', 'id', 'name', 'message', 'error']
        
        # Start with priority fields
        compressed_obj = {}
        for field in priority_fields:
            if field in obj:
                compressed_obj[field] = obj[field]

        # Add other fields if space allows
        for key, value in obj.items():
            if key not in compressed_obj:
                # Try adding this field
                test_obj = compressed_obj.copy()
                test_obj[key] = value
                test_json = json.dumps(test_obj, ensure_ascii=False)
                
                if self._count_text_tokens(test_json) <= max_tokens:
                    compressed_obj[key] = value
                else:
                    # No more space
                    break

        return json.dumps(compressed_obj, ensure_ascii=False)

    def _create_summary_message(self, messages: List[BaseMessage]) -> BaseMessage:
        """
        Create summary for messages (placeholder for future LLM-based summarization)

        Args:
            messages: Messages to summarize

        Returns:
            Summary message
        """
        # TODO: Implement LLM-based summarization for even better compression
        # For now, use rule-based summarization
        summary_parts = []

        for msg in messages:
            if isinstance(msg, (HumanMessage, AIMessage)):
                content_preview = str(msg.content)[:100] if msg.content else ""
                summary_parts.append(f"- {msg.type}: {content_preview}...")

        summary_content = "\n".join(summary_parts)
        return HumanMessage(
            content=f"[CONTEXT SUMMARY]\n{summary_content}\n[END SUMMARY]",
            name="system"
        )

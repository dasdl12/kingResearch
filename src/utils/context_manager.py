# src/utils/context_manager.py
from typing import List, Optional
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)
import logging
import copy

from src.config import load_yaml_config
from src.utils.tokenizer_factory import TokenizerFactory, BaseTokenizer

logger = logging.getLogger(__name__)


def get_search_config():
    config = load_yaml_config("conf.yaml")
    search_config = config.get("MODEL_TOKEN_LIMITS", {})
    return search_config


class ContextManager:
    """Context manager and compression class"""

    def __init__(
        self,
        token_limit: int,
        preserve_prefix_message_count: int = 0,
        llm_type: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize ContextManager

        Args:
            token_limit: Maximum token limit
            preserve_prefix_message_count: Number of messages to preserve at the beginning of the context
            llm_type: Type of LLM (basic, reasoning, vision, code) for tokenizer selection
            model_name: Specific model name for tokenizer selection
        """
        self.token_limit = token_limit
        self.preserve_prefix_message_count = preserve_prefix_message_count
        self.tokenizer = TokenizerFactory.get_tokenizer(llm_type, model_name)

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
        Count tokens in a single message using real tokenizer

        Args:
            message: Message object

        Returns:
            Number of tokens
        """
        return TokenizerFactory.count_message_tokens(message, self.tokenizer)

    def _count_text_tokens(self, text: str) -> int:
        """
        Count tokens in text using real tokenizer

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if not text:
            return 0
        return self.tokenizer.count_tokens(text)

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
        Compress messages to fit within token limit

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
        
        # 详细日志：压缩前的状态
        logger.info(f"[COMPRESS DEBUG] Before compression:")
        logger.info(f"  - Total messages: {len(messages)}")
        logger.info(f"  - Total tokens: {self.count_tokens(messages)}")
        logger.info(f"  - Token limit: {self.token_limit}")
        logger.info(f"  - Preserve prefix count: {self.preserve_prefix_message_count}")
        if len(messages) > 0:
            logger.info(f"  - First 3 message types: {[type(m).__name__ for m in messages[:3]]}")
            logger.info(f"  - First 3 message tokens: {[self._count_message_tokens(m) for m in messages[:3]]}")
        if len(messages) > 3:
            logger.info(f"  - Last 3 message types: {[type(m).__name__ for m in messages[-3:]]}")

        if not self.is_over_limit(messages):
            logger.info("[COMPRESS DEBUG] Messages are within limit, no compression needed")
            return state

        # 2. Compress messages
        compressed_messages = self._compress_messages(messages)

        # 详细日志：压缩后的状态
        logger.info(
            f"Message compression completed: {self.count_tokens(messages)} -> {self.count_tokens(compressed_messages)} tokens"
        )
        logger.info(f"[COMPRESS DEBUG] After compression:")
        logger.info(f"  - Total messages: {len(compressed_messages)}")
        logger.info(f"  - Compressed message types: {[type(m).__name__ for m in compressed_messages[:5]]}")

        state["messages"] = compressed_messages
        
        # 验证返回的 state 确实被压缩了
        final_token_count = self.count_tokens(state["messages"])
        logger.info(f"[COMPRESS DEBUG] Returning state with {len(state['messages'])} messages and {final_token_count} tokens")
        
        return state

    def _compress_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Compress compressible messages while preserving AIMessage-ToolMessage pairs

        Args:
            messages: List of messages to compress

        Returns:
            Compressed message list
        """

        available_token = self.token_limit
        prefix_messages = []

        # 1. Preserve head messages of specified length to retain system prompts and user input
        for i in range(min(self.preserve_prefix_message_count, len(messages))):
            cur_token_cnt = self._count_message_tokens(messages[i])
            if available_token > 0 and available_token >= cur_token_cnt:
                prefix_messages.append(messages[i])
                available_token -= cur_token_cnt
            elif available_token > 0:
                # Truncate content to fit available tokens
                truncated_message = self._truncate_message_content(
                    messages[i], available_token
                )
                prefix_messages.append(truncated_message)
                return prefix_messages
            else:
                break

        # Check if last message in prefix is AIMessage with tool_calls
        # If so, we need to include its ToolMessages in the result
        required_tool_messages = []
        excluded_tool_call_ids = set()  # Track tool_call_ids that should be excluded
        original_prefix_len = len(prefix_messages)  # Remember original length before any modifications
        
        if prefix_messages and isinstance(prefix_messages[-1], AIMessage):
            last_ai_msg = prefix_messages[-1]
            if hasattr(last_ai_msg, 'tool_calls') and last_ai_msg.tool_calls:
                # Extract tool call IDs
                try:
                    tool_call_ids = set()
                    for tc in last_ai_msg.tool_calls:
                        if isinstance(tc, dict) and 'id' in tc:
                            tool_call_ids.add(tc['id'])
                        elif hasattr(tc, 'id'):
                            tool_call_ids.add(tc.id)
                    
                    # Find all corresponding ToolMessages after the prefix
                    # Use original_prefix_len since we haven't modified prefix_messages yet
                    remaining_start_idx = original_prefix_len
                    j = remaining_start_idx
                    while j < len(messages):
                        if isinstance(messages[j], ToolMessage):
                            tool_msg = messages[j]
                            if hasattr(tool_msg, 'tool_call_id') and tool_msg.tool_call_id in tool_call_ids:
                                required_tool_messages.append(messages[j])
                                tool_call_ids.discard(tool_msg.tool_call_id)
                                if not tool_call_ids:
                                    break
                            else:
                                # ToolMessage doesn't belong to our AIMessage, stop
                                break
                        else:
                            # Not a ToolMessage, stop searching
                            break
                        j += 1
                    
                    # Calculate tokens needed for required ToolMessages
                    required_tokens = sum(self._count_message_tokens(msg) for msg in required_tool_messages)
                    
                    # If we don't have enough space for all required ToolMessages,
                    # we must remove the AIMessage from prefix
                    if required_tokens > available_token:
                        # Remove the problematic AIMessage
                        removed_ai_msg = prefix_messages.pop()
                        available_token += self._count_message_tokens(removed_ai_msg)
                        
                        # Track the tool_call_ids that need to be excluded from suffix
                        for tc in removed_ai_msg.tool_calls:
                            if isinstance(tc, dict) and 'id' in tc:
                                excluded_tool_call_ids.add(tc['id'])
                            elif hasattr(tc, 'id'):
                                excluded_tool_call_ids.add(tc.id)
                        
                        required_tool_messages = []
                    else:
                        # We have enough space, reserve it
                        available_token -= required_tokens
                except Exception as e:
                    logger.warning(f"Error processing tool_calls in prefix AIMessage: {e}")
                    required_tool_messages = []

        # 2. Compress subsequent messages from the tail, preserving AIMessage-ToolMessage pairs
        # Skip messages that we already processed (original prefix + required/collected ToolMessages)
        # Use original_prefix_len to ensure we skip the right messages even if AIMessage was removed
        skip_until_idx = original_prefix_len + len(required_tool_messages)
        messages = messages[skip_until_idx:]
        suffix_messages = []
        i = len(messages) - 1
        
        while i >= 0:
            msg = messages[i]
            
            # Never include ToolMessages directly when scanning from tail.
            # They will be added together with their parent AIMessage group.
            if isinstance(msg, ToolMessage):
                i -= 1
                continue
            
            # If this is an AIMessage with tool_calls, we need to keep all corresponding ToolMessages
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                # Collect this AIMessage and all its ToolMessages as a group
                group = [msg]
                group_tokens = self._count_message_tokens(msg)
                
                # Find all corresponding ToolMessages that follow this AIMessage
                j = i + 1
                # Extract tool call IDs from tool_calls
                try:
                    # tool_calls can be dict or object, handle both cases
                    tool_call_ids = set()
                    for tc in msg.tool_calls:
                        if isinstance(tc, dict):
                            if 'id' in tc:
                                tool_call_ids.add(tc['id'])
                        elif hasattr(tc, 'id'):
                            tool_call_ids.add(tc.id)
                except Exception:
                    # If we can't extract IDs, just count consecutive ToolMessages
                    tool_call_ids = None
                
                # Collect consecutive ToolMessages after this AIMessage
                while j < len(messages):
                    if isinstance(messages[j], ToolMessage):
                        # Check if this ToolMessage belongs to our AIMessage
                        if tool_call_ids is None:
                            # No ID check, just take consecutive ToolMessages
                            # Count how many tool_calls we have
                            if len(group) - 1 < len(msg.tool_calls):
                                group.append(messages[j])
                                group_tokens += self._count_message_tokens(messages[j])
                            else:
                                break
                        else:
                            # Check if ToolMessage's tool_call_id matches
                            tool_msg = messages[j]
                            if hasattr(tool_msg, 'tool_call_id') and tool_msg.tool_call_id in tool_call_ids:
                                group.append(tool_msg)
                                group_tokens += self._count_message_tokens(tool_msg)
                            else:
                                # This ToolMessage doesn't belong to our AIMessage
                                break
                        j += 1
                    else:
                        # Not a ToolMessage, stop collecting
                        break
                
                # Check if we have enough space for the entire group
                if available_token >= group_tokens:
                    suffix_messages = group + suffix_messages
                    available_token -= group_tokens
                # If not enough space, skip the entire group to maintain consistency
                
                i -= 1
            else:
                # Regular message processing (not an AIMessage with tool_calls)
                cur_token_cnt = self._count_message_tokens(msg)
                
                if cur_token_cnt > 0 and available_token >= cur_token_cnt:
                    suffix_messages = [msg] + suffix_messages
                    available_token -= cur_token_cnt
                elif available_token > 0:
                    # Truncate content to fit available tokens
                    truncated_message = self._truncate_message_content(
                        msg, available_token
                    )
                    suffix_messages = [truncated_message] + suffix_messages
                    return prefix_messages + required_tool_messages + suffix_messages
                
                i -= 1

        # Merge parts
        merged_messages = prefix_messages + required_tool_messages + suffix_messages

        # Final safety: remove any orphan ToolMessage whose tool_call_id
        # does not have a corresponding AIMessage.tool_calls in the merged list
        try:
            included_tool_call_ids = set()
            for m in merged_messages:
                if isinstance(m, AIMessage) and hasattr(m, 'tool_calls') and m.tool_calls:
                    for tc in m.tool_calls:
                        if isinstance(tc, dict) and 'id' in tc:
                            included_tool_call_ids.add(tc['id'])
                        elif hasattr(tc, 'id'):
                            included_tool_call_ids.add(tc.id)

            filtered_messages: List[BaseMessage] = []
            for m in merged_messages:
                if isinstance(m, ToolMessage) and hasattr(m, 'tool_call_id'):
                    if m.tool_call_id not in included_tool_call_ids:
                        # Drop orphan ToolMessage
                        continue
                filtered_messages.append(m)

            return filtered_messages
        except Exception as e:
            logger.warning(f"[COMPRESS DEBUG] Failed to filter orphan ToolMessages: {e}")
            return merged_messages

    def _truncate_message_content(
        self, message: BaseMessage, max_tokens: int
    ) -> BaseMessage:
        """
        Truncate message content while preserving all other attributes by copying the original message
        and only modifying its content attribute. Truncation is done at token boundaries using real tokenizer.

        Args:
            message: The message to truncate
            max_tokens: Maximum number of tokens to keep

        Returns:
            New message instance with truncated content
        """

        # Create a deep copy of the original message to preserve all attributes
        truncated_message = copy.deepcopy(message)

        # Truncate only the content attribute using tokenizer (at token boundaries, not character boundaries)
        if isinstance(message.content, str):
            truncated_message.content = self.tokenizer.truncate_text(
                message.content, max_tokens
            )
        else:
            # If content is not a string, keep as is
            truncated_message.content = message.content

        return truncated_message

    def _create_summary_message(self, messages: List[BaseMessage]) -> BaseMessage:
        """
        Create summary for messages

        Args:
            messages: Messages to summarize

        Returns:
            Summary message
        """
        # TODO: summary implementation
        pass

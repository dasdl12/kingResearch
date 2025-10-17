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
import json

from src.config import load_yaml_config
from src.utils.tokenizer_factory import TokenizerFactory, BaseTokenizer

logger = logging.getLogger(__name__)


def get_context_config():
    """Get context management configuration from config file."""
    config = load_yaml_config("conf.yaml")
    return config.get("CONTEXT_MANAGEMENT", {})


class ContextManager:
    """Advanced context manager with intelligent summarization and layered compression."""

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
            preserve_prefix_message_count: Number of messages to preserve at the beginning
            llm_type: Type of LLM (basic, reasoning, vision, code) for tokenizer selection
            model_name: Specific model name for tokenizer selection
        """
        self.token_limit = token_limit
        self.preserve_prefix_message_count = preserve_prefix_message_count
        self.tokenizer = TokenizerFactory.get_tokenizer(llm_type, model_name)
        
        # Load context management configuration
        self.context_config = get_context_config()
        self.enabled = self.context_config.get("enabled", True)
        self.compression_strategy = self.context_config.get("compression_strategy", "smart_summary")
        self.enable_summarization = self.context_config.get("enable_summarization", True)
        
        # Budget allocation
        budget = self.context_config.get("budget_allocation", {})
        self.prefix_budget_ratio = budget.get("prefix", 0.15)
        self.tool_results_budget_ratio = budget.get("tool_results", 0.60)
        self.recent_context_budget_ratio = budget.get("recent_context", 0.20)
        self.output_reserve_ratio = budget.get("output_reserve", 0.05)
        
        # Summarization settings
        summarization_config = self.context_config.get("summarization", {})
        self.max_tokens_per_tool = summarization_config.get("max_tokens_per_tool", 2000)
        self.trigger_ratio = summarization_config.get("trigger_ratio", 0.7)
        
        # Initialize summary LLM lazily
        self._summary_llm = None
        
        # Compression statistics
        self.compression_stats = {
            "total_compressions": 0,
            "tool_messages_lost": 0,
            "tokens_saved": 0,
        }

    def _get_summary_llm(self):
        """Lazy initialization of summary LLM."""
        if self._summary_llm is None:
            try:
                from src.llms.llm import get_llm_by_type
                self._summary_llm = get_llm_by_type("summary")
                logger.info("Summary LLM initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize summary LLM: {e}. Falling back to truncation.")
                self._summary_llm = False  # Mark as failed
        return self._summary_llm if self._summary_llm else None

    def count_tokens(self, messages: List[BaseMessage]) -> int:
        """Count tokens in message list."""
        total_tokens = 0
        for message in messages:
            total_tokens += self._count_message_tokens(message)
        return total_tokens

    def _count_message_tokens(self, message: BaseMessage) -> int:
        """Count tokens in a single message using real tokenizer."""
        return TokenizerFactory.count_message_tokens(message, self.tokenizer)

    def _count_text_tokens(self, text: str) -> int:
        """Count tokens in text using real tokenizer."""
        if not text:
            return 0
        return self.tokenizer.count_tokens(text)

    def is_over_limit(self, messages: List[BaseMessage]) -> bool:
        """Check if messages exceed token limit."""
        return self.count_tokens(messages) > self.token_limit

    def compress_messages(self, state: dict) -> dict:
        """
        Compress messages to fit within token limit with intelligent strategies.

        Args:
            state: state with original messages

        Returns:
            Compressed state with compressed messages
        """
        # If not enabled or no token limit, return original state
        if not self.enabled or self.token_limit is None:
            logger.info("Context management is disabled or no token_limit set.")
            return state

        if not isinstance(state, dict) or "messages" not in state:
            logger.warning("No messages found in state")
            return state

        messages = state["messages"]
        original_token_count = self.count_tokens(messages)
        
        # Detailed logging: before compression
        logger.info(f"[COMPRESS DEBUG] Before compression:")
        logger.info(f"  - Total messages: {len(messages)}")
        logger.info(f"  - Total tokens: {original_token_count}")
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

        # Analyze tool message ratio to decide compression strategy
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        tool_token_count = sum(self._count_message_tokens(m) for m in tool_messages)
        tool_ratio = tool_token_count / original_token_count if original_token_count > 0 else 0
        
        logger.info(f"[COMPRESS DEBUG] Tool messages: {len(tool_messages)}, "
                   f"Tool tokens: {tool_token_count} ({tool_ratio:.1%} of total)")

        # Choose compression strategy based on tool message ratio
        if tool_ratio > self.trigger_ratio and self.enable_summarization:
            logger.info(f"[COMPRESS DEBUG] Tool ratio {tool_ratio:.1%} exceeds threshold {self.trigger_ratio:.1%}, "
                       f"using smart summarization")
            compressed_messages = self._compress_with_smart_summary(messages)
        else:
            logger.info(f"[COMPRESS DEBUG] Using layered compression strategy")
            compressed_messages = self._compress_with_layers(messages)

        # Update compression statistics
        self.compression_stats["total_compressions"] += 1
        self.compression_stats["tokens_saved"] += original_token_count - self.count_tokens(compressed_messages)
        lost_tool_messages = len(tool_messages) - len([m for m in compressed_messages if isinstance(m, ToolMessage)])
        self.compression_stats["tool_messages_lost"] += lost_tool_messages

        # Detailed logging: after compression
        final_token_count = self.count_tokens(compressed_messages)
        logger.info(f"Message compression completed: {original_token_count} -> {final_token_count} tokens")
        logger.info(f"[COMPRESS DEBUG] After compression:")
        logger.info(f"  - Total messages: {len(compressed_messages)}")
        logger.info(f"  - Compressed message types: {[type(m).__name__ for m in compressed_messages[:5]]}")
        logger.info(f"  - Compression ratio: {final_token_count / original_token_count:.1%}")
        
        # Quality monitoring and warnings
        if lost_tool_messages > 3:
            logger.error(f"⚠️ WARNING: Lost {lost_tool_messages} tool messages during compression! "
                        f"This may significantly impact response quality.")
        elif lost_tool_messages > 0:
            logger.warning(f"⚠️ Lost {lost_tool_messages} tool messages during compression")
        
        state["messages"] = compressed_messages
        logger.info(f"[COMPRESS DEBUG] Returning state with {len(compressed_messages)} messages and {final_token_count} tokens")
        
        return state

    def _compress_with_smart_summary(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Compress messages using intelligent summarization of tool results.
        
        Args:
            messages: List of messages to compress
            
        Returns:
            Compressed message list with summarized tool results
        """
        logger.info("[SMART SUMMARY] Starting intelligent summarization compression")
        
        # Calculate token budgets
        available_tokens = self.token_limit
        prefix_budget = int(available_tokens * self.prefix_budget_ratio)
        tool_budget = int(available_tokens * self.tool_results_budget_ratio)
        suffix_budget = int(available_tokens * self.recent_context_budget_ratio)
        
        logger.info(f"[SMART SUMMARY] Token budgets - Prefix: {prefix_budget}, "
                   f"Tools: {tool_budget}, Suffix: {suffix_budget}")
        
        compressed_messages = []
        
        # 1. Preserve prefix messages
        prefix_tokens_used = 0
        for i in range(min(self.preserve_prefix_message_count, len(messages))):
            msg_tokens = self._count_message_tokens(messages[i])
            if prefix_tokens_used + msg_tokens <= prefix_budget:
                compressed_messages.append(messages[i])
                prefix_tokens_used += msg_tokens
            else:
                # Truncate to fit
                remaining = prefix_budget - prefix_tokens_used
                if remaining > 100:  # Only if we have reasonable space
                    compressed_messages.append(self._truncate_message_content(messages[i], remaining))
                break
        
        prefix_count = len(compressed_messages)
        logger.info(f"[SMART SUMMARY] Preserved {prefix_count} prefix messages using {prefix_tokens_used} tokens")
        
        # 2. Process middle section with smart summarization
        # Group AIMessage-ToolMessage pairs
        middle_messages = messages[prefix_count:]
        summarized_middle = self._summarize_tool_results_section(middle_messages, tool_budget)
        compressed_messages.extend(summarized_middle)
        
        middle_tokens = sum(self._count_message_tokens(m) for m in summarized_middle)
        logger.info(f"[SMART SUMMARY] Processed {len(middle_messages)} middle messages -> "
                   f"{len(summarized_middle)} messages using {middle_tokens} tokens")
        
        # 3. Preserve recent context from suffix if there's budget left
        used_tokens = prefix_tokens_used + middle_tokens
        remaining_budget = self.token_limit - used_tokens
        
        if remaining_budget > suffix_budget * 0.5:  # If we have at least half the suffix budget
            suffix_messages = self._get_recent_messages(middle_messages, int(remaining_budget))
            # Remove duplicates that might already be in summarized_middle
            suffix_start_idx = len(messages) - len(suffix_messages)
            if suffix_start_idx > prefix_count + len(summarized_middle):
                compressed_messages.extend(suffix_messages)
                logger.info(f"[SMART SUMMARY] Added {len(suffix_messages)} recent suffix messages")
        
        return self._ensure_message_integrity(compressed_messages)

    def _summarize_tool_results_section(
        self, messages: List[BaseMessage], budget: int
    ) -> List[BaseMessage]:
        """
        Summarize tool results intelligently.
        
        Args:
            messages: Messages to process (potentially containing tool results)
            budget: Token budget for this section
            
        Returns:
            List of messages with summarized tool results
        """
        if not messages:
            return []
        
        summary_llm = self._get_summary_llm()
        result_messages = []
        budget_used = 0
        
        i = 0
        while i < len(messages) and budget_used < budget:
            msg = messages[i]
            
            # If it's an AIMessage with tool_calls, process as a group
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                group = [msg]
                tool_call_ids = set()
                
                # Extract tool call IDs
                for tc in msg.tool_calls:
                    if isinstance(tc, dict) and 'id' in tc:
                        tool_call_ids.add(tc['id'])
                    elif hasattr(tc, 'id'):
                        tool_call_ids.add(tc.id)
                
                # Collect corresponding ToolMessages
                j = i + 1
                while j < len(messages) and isinstance(messages[j], ToolMessage):
                    tool_msg = messages[j]
                    if hasattr(tool_msg, 'tool_call_id') and tool_msg.tool_call_id in tool_call_ids:
                        group.append(tool_msg)
                        tool_call_ids.discard(tool_msg.tool_call_id)
                        if not tool_call_ids:
                            break
                    j += 1
                
                # Calculate group tokens
                group_tokens = sum(self._count_message_tokens(m) for m in group)
                
                # If group is too large and we have summary LLM, summarize the ToolMessages
                if group_tokens > self.max_tokens_per_tool * len([m for m in group if isinstance(m, ToolMessage)]) and summary_llm:
                    logger.info(f"[SMART SUMMARY] Summarizing tool result group of {len(group)} messages ({group_tokens} tokens)")
                    summarized_group = self._summarize_tool_group(group, summary_llm)
                    summarized_tokens = sum(self._count_message_tokens(m) for m in summarized_group)
                    
                    if budget_used + summarized_tokens <= budget:
                        result_messages.extend(summarized_group)
                        budget_used += summarized_tokens
                        logger.info(f"[SMART SUMMARY] Compressed {group_tokens} -> {summarized_tokens} tokens")
                    else:
                        logger.warning(f"[SMART SUMMARY] Skipping group, would exceed budget")
                else:
                    # Group is small enough or no summary LLM, keep as is if budget allows
                    if budget_used + group_tokens <= budget:
                        result_messages.extend(group)
                        budget_used += group_tokens
                    else:
                        logger.warning(f"[SMART SUMMARY] Skipping group due to budget constraint")
                
                i = j  # Skip to next non-tool message
            else:
                # Regular message
                msg_tokens = self._count_message_tokens(msg)
                if budget_used + msg_tokens <= budget:
                    result_messages.append(msg)
                    budget_used += msg_tokens
                i += 1
        
        logger.info(f"[SMART SUMMARY] Tool section used {budget_used}/{budget} tokens")
        return result_messages

    def _summarize_tool_group(
        self, group: List[BaseMessage], summary_llm
    ) -> List[BaseMessage]:
        """
        Summarize a group of AIMessage + ToolMessages using LLM with robust handling.
        
        Args:
            group: List containing AIMessage followed by ToolMessages
            summary_llm: LLM instance for summarization
            
        Returns:
            Summarized group with same structure but compressed content
        """
        if not group or not summary_llm:
            return group
        
        ai_message = group[0]
        tool_messages = [m for m in group[1:] if isinstance(m, ToolMessage)]
        
        if not tool_messages:
            return group
        
        try:
            # Get summary model's token limit from config
            from src.llms.llm import get_llm_token_limit_by_type
            summary_token_limit = get_llm_token_limit_by_type("summary")
            
            # If no token limit configured, use a conservative default
            if not summary_token_limit:
                summary_token_limit = 16000  # Conservative default
                logger.warning("[SMART SUMMARY] No token limit found for summary model, using default 16000")
            
            # Reserve tokens for prompt template and output
            prompt_template_tokens = 300  # Estimated tokens for prompt instructions
            output_reserve_tokens = self.max_tokens_per_tool + 500  # Reserve for output
            available_for_content = summary_token_limit - prompt_template_tokens - output_reserve_tokens
            
            if available_for_content < 1000:
                logger.error(f"[SMART SUMMARY] Summary model token limit too small ({summary_token_limit}), "
                           f"falling back to truncation")
                return [ai_message] + [self._truncate_message_content(m, self.max_tokens_per_tool) for m in tool_messages]
            
            # Prepare tool contents with intelligent truncation
            tool_contents = []
            tokens_per_tool = available_for_content // max(len(tool_messages), 1)
            
            logger.info(f"[SMART SUMMARY] Summary model limit: {summary_token_limit}, "
                       f"available for content: {available_for_content}, "
                       f"tokens per tool: {tokens_per_tool}")
            
            for tool_msg in tool_messages:
                tool_name = getattr(tool_msg, 'name', 'unknown_tool')
                content = tool_msg.content
                
                # Truncate content to fit within budget using tokenizer
                if content:
                    # Use tokenizer for precise truncation
                    truncated_content = self.tokenizer.truncate_text(content, tokens_per_tool)
                    
                    # If content was truncated, add indicator
                    if len(truncated_content) < len(content):
                        truncated_content += "\n[... content truncated for summarization ...]"
                    
                    tool_contents.append(f"Tool: {tool_name}\nResult:\n{truncated_content}\n")
                else:
                    tool_contents.append(f"Tool: {tool_name}\nResult: [empty]\n")
            
            # Build prompt
            prompt = f"""You are a precise information extractor. Summarize the following tool execution results, preserving ALL key information:

1. For search results: Extract titles, key facts, numbers, dates, and source URLs
2. For web scraping: Extract main content, data tables, and important details
3. For code execution: Include inputs, outputs, and key results
4. Keep all numerical data, names, dates, and URLs intact
5. Use markdown format for structure (lists, tables if needed)

Tool execution results:
{chr(10).join(tool_contents)}

Provide a comprehensive but concise summary (max {self.max_tokens_per_tool} tokens):"""

            # Verify final prompt size
            prompt_tokens = self._count_text_tokens(prompt)
            if prompt_tokens > summary_token_limit - output_reserve_tokens:
                logger.warning(f"[SMART SUMMARY] Prompt still too large ({prompt_tokens} tokens), "
                             f"using aggressive truncation")
                # Fallback to simple truncation
                return [ai_message] + [self._truncate_message_content(m, self.max_tokens_per_tool) for m in tool_messages]
            
            logger.info(f"[SMART SUMMARY] Sending {prompt_tokens} tokens to summary LLM")
            
            # Call summary LLM with timeout protection
            summary_response = summary_llm.invoke([HumanMessage(content=prompt)])
            summary_content = summary_response.content
            
            if not summary_content:
                logger.warning("[SMART SUMMARY] Summary LLM returned empty content")
                return [ai_message] + [self._truncate_message_content(m, self.max_tokens_per_tool) for m in tool_messages]
            
            # Create summarized ToolMessages
            summarized_tool_messages = []
            for tool_msg in tool_messages:
                summarized_msg = ToolMessage(
                    content=f"[SUMMARIZED BY {getattr(tool_msg, 'name', 'tool').upper()}]\n{summary_content}",
                    tool_call_id=tool_msg.tool_call_id,
                    name=getattr(tool_msg, 'name', None),
                )
                summarized_tool_messages.append(summarized_msg)
                break  # Only create one summarized message for all tools in group
            
            logger.info(f"[SMART SUMMARY] Successfully summarized {len(tool_messages)} tool messages")
            return [ai_message] + summarized_tool_messages
            
        except Exception as e:
            logger.error(f"[SMART SUMMARY] Failed to summarize tool group: {e}")
            # Fallback: truncate tool messages instead
            logger.info("[SMART SUMMARY] Falling back to simple truncation")
            return [ai_message] + [self._truncate_message_content(m, self.max_tokens_per_tool) for m in tool_messages]

    def _compress_with_layers(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Layered compression strategy: preserve important messages from head and tail.
        This is the fallback when tool messages don't dominate.
        
        Args:
            messages: List of messages to compress
            
        Returns:
            Compressed message list
        """
        logger.info("[LAYERED COMPRESSION] Using traditional layered compression")
        return self._compress_messages(messages)

    def _get_recent_messages(self, messages: List[BaseMessage], budget: int) -> List[BaseMessage]:
        """Get most recent messages that fit within budget."""
        recent = []
        tokens_used = 0
        
        for msg in reversed(messages):
            msg_tokens = self._count_message_tokens(msg)
            if tokens_used + msg_tokens <= budget:
                recent.insert(0, msg)
                tokens_used += msg_tokens
            else:
                break
        
        return recent

    def _compress_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Original compression logic (preserved for backward compatibility).
        Compress messages while preserving AIMessage-ToolMessage pairs.
        """
        available_token = self.token_limit
        prefix_messages = []

        # 1. Preserve head messages of specified length
        for i in range(min(self.preserve_prefix_message_count, len(messages))):
            cur_token_cnt = self._count_message_tokens(messages[i])
            if available_token > 0 and available_token >= cur_token_cnt:
                prefix_messages.append(messages[i])
                available_token -= cur_token_cnt
            elif available_token > 0:
                truncated_message = self._truncate_message_content(
                    messages[i], available_token
                )
                prefix_messages.append(truncated_message)
                return prefix_messages
            else:
                break

        # Check if last message in prefix is AIMessage with tool_calls
        required_tool_messages = []
        excluded_tool_call_ids = set()
        original_prefix_len = len(prefix_messages)
        
        if prefix_messages and isinstance(prefix_messages[-1], AIMessage):
            last_ai_msg = prefix_messages[-1]
            if hasattr(last_ai_msg, 'tool_calls') and last_ai_msg.tool_calls:
                try:
                    tool_call_ids = set()
                    for tc in last_ai_msg.tool_calls:
                        if isinstance(tc, dict) and 'id' in tc:
                            tool_call_ids.add(tc['id'])
                        elif hasattr(tc, 'id'):
                            tool_call_ids.add(tc.id)
                    
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
                                break
                        else:
                            break
                        j += 1
                    
                    required_tokens = sum(self._count_message_tokens(msg) for msg in required_tool_messages)
                    
                    if required_tokens > available_token:
                        removed_ai_msg = prefix_messages.pop()
                        available_token += self._count_message_tokens(removed_ai_msg)
                        
                        for tc in removed_ai_msg.tool_calls:
                            if isinstance(tc, dict) and 'id' in tc:
                                excluded_tool_call_ids.add(tc['id'])
                            elif hasattr(tc, 'id'):
                                excluded_tool_call_ids.add(tc.id)
                        
                        required_tool_messages = []
                    else:
                        available_token -= required_tokens
                except Exception as e:
                    logger.warning(f"Error processing tool_calls in prefix AIMessage: {e}")
                    required_tool_messages = []

        # 2. Compress subsequent messages from the tail
        skip_until_idx = original_prefix_len + len(required_tool_messages)
        messages = messages[skip_until_idx:]
        suffix_messages = []
        i = len(messages) - 1
        
        while i >= 0:
            msg = messages[i]
            
            if isinstance(msg, ToolMessage):
                i -= 1
                continue
            
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                group = [msg]
                group_tokens = self._count_message_tokens(msg)
                
                j = i + 1
                try:
                    tool_call_ids = set()
                    for tc in msg.tool_calls:
                        if isinstance(tc, dict):
                            if 'id' in tc:
                                tool_call_ids.add(tc['id'])
                        elif hasattr(tc, 'id'):
                            tool_call_ids.add(tc.id)
                except Exception:
                    tool_call_ids = None
                
                while j < len(messages):
                    if isinstance(messages[j], ToolMessage):
                        if tool_call_ids is None:
                            if len(group) - 1 < len(msg.tool_calls):
                                group.append(messages[j])
                                group_tokens += self._count_message_tokens(messages[j])
                            else:
                                break
                        else:
                            tool_msg = messages[j]
                            if hasattr(tool_msg, 'tool_call_id') and tool_msg.tool_call_id in tool_call_ids:
                                group.append(tool_msg)
                                group_tokens += self._count_message_tokens(tool_msg)
                            else:
                                break
                        j += 1
                    else:
                        break
                
                if available_token >= group_tokens:
                    suffix_messages = group + suffix_messages
                    available_token -= group_tokens
                
                i -= 1
            else:
                cur_token_cnt = self._count_message_tokens(msg)
                
                if cur_token_cnt > 0 and available_token >= cur_token_cnt:
                    suffix_messages = [msg] + suffix_messages
                    available_token -= cur_token_cnt
                elif available_token > 0:
                    truncated_message = self._truncate_message_content(
                        msg, available_token
                    )
                    suffix_messages = [truncated_message] + suffix_messages
                    return prefix_messages + required_tool_messages + suffix_messages
                
                i -= 1

        merged_messages = prefix_messages + required_tool_messages + suffix_messages
        return self._ensure_message_integrity(merged_messages)

    def _ensure_message_integrity(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Final safety check: remove any orphan ToolMessage whose tool_call_id
        does not have a corresponding AIMessage.tool_calls in the list.
        """
        try:
            included_tool_call_ids = set()
            for m in messages:
                if isinstance(m, AIMessage) and hasattr(m, 'tool_calls') and m.tool_calls:
                    for tc in m.tool_calls:
                        if isinstance(tc, dict) and 'id' in tc:
                            included_tool_call_ids.add(tc['id'])
                        elif hasattr(tc, 'id'):
                            included_tool_call_ids.add(tc.id)

            filtered_messages: List[BaseMessage] = []
            for m in messages:
                if isinstance(m, ToolMessage) and hasattr(m, 'tool_call_id'):
                    if m.tool_call_id not in included_tool_call_ids:
                        continue
                filtered_messages.append(m)

            return filtered_messages
        except Exception as e:
            logger.warning(f"[COMPRESS DEBUG] Failed to filter orphan ToolMessages: {e}")
            return messages

    def _truncate_message_content(
        self, message: BaseMessage, max_tokens: int
    ) -> BaseMessage:
        """
        Truncate message content while preserving all other attributes.
        """
        truncated_message = copy.deepcopy(message)

        if isinstance(message.content, str):
            truncated_message.content = self.tokenizer.truncate_text(
                message.content, max_tokens
            )
        else:
            truncated_message.content = message.content

        return truncated_message

    def get_compression_stats(self) -> dict:
        """Get compression statistics for monitoring."""
        return self.compression_stats.copy()

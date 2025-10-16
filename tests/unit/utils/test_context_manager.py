import pytest
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from src.utils.context_manager import ContextManager


# Use a consistent model for testing
TEST_MODEL = "gpt-4"


class TestContextManager:
    """Test cases for ContextManager"""

    def test_count_tokens_with_empty_messages(self):
        """Test counting tokens with empty message list"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        messages = []
        token_count = context_manager.count_tokens(messages)
        assert token_count == 0

    def test_count_tokens_with_system_message(self):
        """Test counting tokens with system message"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        messages = [SystemMessage(content="You are a helpful assistant.")]
        token_count = context_manager.count_tokens(messages)
        # With real tokenizer, should have reasonable token count
        assert token_count > 0
        assert token_count < 20  # Should be less than 20 tokens

    def test_count_tokens_with_human_message(self):
        """Test counting tokens with human message"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        messages = [HumanMessage(content="你好，这是一个测试消息。")]
        token_count = context_manager.count_tokens(messages)
        # Should have reasonable token count for Chinese text
        assert token_count > 5
        assert token_count < 30

    def test_count_tokens_with_ai_message(self):
        """Test counting tokens with AI message"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        messages = [AIMessage(content="I'm doing well, thank you for asking!")]
        token_count = context_manager.count_tokens(messages)
        assert token_count > 0
        assert token_count < 25

    def test_count_tokens_with_tool_message(self):
        """Test counting tokens with tool message"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        messages = [
            ToolMessage(content="Tool execution result data here", tool_call_id="test")
        ]
        token_count = context_manager.count_tokens(messages)
        assert token_count > 0
        assert token_count < 30

    def test_count_tokens_with_multiple_messages(self):
        """Test counting tokens with multiple messages"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello, how are you?"),
            AIMessage(content="I'm doing well, thank you for asking!"),
        ]
        token_count = context_manager.count_tokens(messages)
        # Should be sum of all individual message tokens
        assert token_count > 10
        assert token_count < 100

    def test_is_over_limit_when_under_limit(self):
        """Test is_over_limit when messages are under token limit"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        short_messages = [HumanMessage(content="Short message")]
        is_over = context_manager.is_over_limit(short_messages)
        assert is_over is False

    def test_is_over_limit_when_over_limit(self):
        """Test is_over_limit when messages exceed token limit"""
        # Create a context manager with a very low limit
        low_limit_cm = ContextManager(token_limit=5, model_name=TEST_MODEL)
        long_messages = [
            HumanMessage(
                content="This is a very long message that should exceed the limit"
            )
        ]
        is_over = low_limit_cm.is_over_limit(long_messages)
        assert is_over is True

    def test_compress_messages_when_not_over_limit(self):
        """Test compress_messages when messages are not over limit"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        messages = [HumanMessage(content="Short message")]
        compressed = context_manager.compress_messages({"messages": messages})
        # Should return the same messages when not over limit
        assert len(compressed["messages"]) == len(messages)

    def test_compress_messages_with_system_message(self):
        """Test compress_messages preserves system message"""
        # Create a context manager with limited token capacity
        limited_cm = ContextManager(token_limit=200, model_name=TEST_MODEL)

        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            HumanMessage(
                content="Can you tell me a very long story that would exceed token limits? "
                * 100
            ),
        ]

        compressed = limited_cm.compress_messages({"messages": messages})
        # Should have fewer messages or truncated messages
        assert len(compressed["messages"]) >= 1
        # Total tokens should be close to limit (allow small overhead for message structure)
        # The overhead comes from message structure (type, metadata, etc.)
        assert limited_cm.count_tokens(compressed["messages"]) <= 210  # Allow 10 tokens overhead

    def test_compress_messages_with_preserve_prefix_message(self):
        """Test compress_messages when no system message is present"""
        # Create a context manager with limited token capacity
        limited_cm = ContextManager(
            token_limit=100, preserve_prefix_message_count=2, model_name=TEST_MODEL
        )

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            HumanMessage(
                content="Can you tell me a very long story that would exceed token limits? "
                * 10
            ),
        ]

        compressed = limited_cm.compress_messages({"messages": messages})
        # Should keep messages within token limit
        assert len(compressed["messages"]) >= 1
        # Total tokens should be close to limit (allow small overhead for message structure)
        assert limited_cm.count_tokens(compressed["messages"]) <= 110  # Allow 10 tokens overhead

    def test_compress_messages_without_config(self):
        """Test compress_messages preserves system message"""
        # Create a context manager with limited token capacity
        limited_cm = ContextManager(None)

        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            HumanMessage(
                content="Can you tell me a very long story that would exceed token limits? "
                * 100
            ),
        ]

        compressed = limited_cm.compress_messages({"messages": messages})
        # return the original messages
        assert len(compressed["messages"]) == 4


    def test_count_message_tokens_with_additional_kwargs(self):
        """Test counting tokens for messages with additional kwargs"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        message = ToolMessage(
            content="Tool result",
            tool_call_id="test",
            additional_kwargs={"tool_calls": [{"name": "test_function"}]},
        )
        token_count = context_manager._count_message_tokens(message)
        assert token_count > 0
        assert token_count < 50

    def test_count_message_tokens_minimum_one_token(self):
        """Test that message token count is at least 1"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        message = HumanMessage(content="")  # Empty content
        token_count = context_manager._count_message_tokens(message)
        assert token_count >= 1  # Should be at least 1

    def test_count_text_tokens_english_only(self):
        """Test counting tokens for English text"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        text = "This is a test."
        token_count = context_manager._count_text_tokens(text)
        assert token_count > 0
        assert token_count < 15  # Should be reasonable

    def test_count_text_tokens_chinese_only(self):
        """Test counting tokens for Chinese text"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        text = "这是一个测试文本"
        token_count = context_manager._count_text_tokens(text)
        # Real tokenizer will have different count than character-based estimation
        assert token_count > 0
        assert token_count < 20

    def test_count_text_tokens_mixed_content(self):
        """Test counting tokens for mixed English and Chinese text"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)
        text = "Hello world 这是一些中文"
        token_count = context_manager._count_text_tokens(text)
        assert token_count > 0
        assert token_count < 30

    def test_truncate_at_token_boundaries(self):
        """Test that truncation happens at token boundaries, not character boundaries"""
        context_manager = ContextManager(token_limit=1000, model_name=TEST_MODEL)

        text = "This is a longer text that will be truncated at token boundaries."
        max_tokens = 5

        truncated_message = context_manager._truncate_message_content(
            HumanMessage(content=text), max_tokens
        )

        # Verify truncated text is valid
        assert isinstance(truncated_message.content, str)
        assert len(truncated_message.content) > 0
        assert len(truncated_message.content) <= len(text)

        # Verify token count is within limit
        truncated_tokens = context_manager._count_text_tokens(
            truncated_message.content
        )
        assert truncated_tokens <= max_tokens

    def test_compress_messages_preserves_aimessage_toolmessage_pairs(self):
        """Test that compression preserves AIMessage-ToolMessage pairs"""
        # Create a context manager with limited token capacity
        limited_cm = ContextManager(
            token_limit=300, preserve_prefix_message_count=2, model_name=TEST_MODEL
        )

        # Create an AIMessage with tool_calls
        ai_message_with_tools = AIMessage(
            content="I'll search for that information.",
            tool_calls=[
                {"name": "web_search", "args": {"query": "test query 1"}, "id": "call_1", "type": "tool_call"},
                {"name": "web_search", "args": {"query": "test query 2"}, "id": "call_2", "type": "tool_call"},
                {"name": "web_search", "args": {"query": "test query 3"}, "id": "call_3", "type": "tool_call"},
            ]
        )

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            ai_message_with_tools,
            ToolMessage(content="Result 1 " * 100, tool_call_id="call_1"),  # Large result
            ToolMessage(content="Result 2 " * 100, tool_call_id="call_2"),  # Large result
            ToolMessage(content="Result 3 " * 100, tool_call_id="call_3"),  # Large result
            HumanMessage(content="Final message"),
        ]

        compressed = limited_cm.compress_messages({"messages": messages})
        compressed_messages = compressed["messages"]

        # Verify: If AIMessage with tool_calls is present, ALL its ToolMessages must be present
        ai_messages_with_tools = [
            msg for msg in compressed_messages 
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls
        ]

        for ai_msg in ai_messages_with_tools:
            # Extract tool call IDs
            tool_call_ids = set()
            for tc in ai_msg.tool_calls:
                if isinstance(tc, dict) and 'id' in tc:
                    tool_call_ids.add(tc['id'])
                elif hasattr(tc, 'id'):
                    tool_call_ids.add(tc.id)

            # Find all ToolMessages in compressed messages
            tool_messages = [
                msg for msg in compressed_messages 
                if isinstance(msg, ToolMessage)
            ]

            # Count how many of our tool_calls have corresponding ToolMessages
            found_tool_call_ids = set()
            for tool_msg in tool_messages:
                if hasattr(tool_msg, 'tool_call_id') and tool_msg.tool_call_id in tool_call_ids:
                    found_tool_call_ids.add(tool_msg.tool_call_id)

            # Either all tool_calls should have their ToolMessages, or the AIMessage should be excluded
            assert found_tool_call_ids == tool_call_ids, (
                f"AIMessage with tool_calls present but not all ToolMessages found. "
                f"Expected: {tool_call_ids}, Found: {found_tool_call_ids}"
            )

        # Verify total tokens are within limit (with small overhead allowance)
        assert limited_cm.count_tokens(compressed_messages) <= 310

    def test_compress_messages_excludes_incomplete_tool_pairs(self):
        """Test that compression excludes AIMessage-ToolMessage groups that don't fit"""
        # Create a very small token limit
        limited_cm = ContextManager(
            token_limit=50, preserve_prefix_message_count=1, model_name=TEST_MODEL
        )

        # Create messages where the tool group is too large to fit
        ai_message_with_tools = AIMessage(
            content="Searching...",
            tool_calls=[
                {"name": "web_search", "args": {"query": "test"}, "id": "call_1", "type": "tool_call"},
            ]
        )

        messages = [
            HumanMessage(content="Hello"),
            ai_message_with_tools,
            ToolMessage(
                content="This is a very long result that will exceed token limits when combined with the AIMessage " * 20,
                tool_call_id="call_1"
            ),
            HumanMessage(content="Final message"),
        ]

        compressed = limited_cm.compress_messages({"messages": messages})
        compressed_messages = compressed["messages"]

        # Verify: AIMessage with tool_calls should NOT be present if its ToolMessages can't fit
        ai_messages_with_tools = [
            msg for msg in compressed_messages 
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls
        ]

        # For any AIMessage with tool_calls that IS present, all ToolMessages must be present
        for ai_msg in ai_messages_with_tools:
            tool_call_ids = {tc.get('id') if isinstance(tc, dict) else tc.id for tc in ai_msg.tool_calls}
            tool_messages = [
                msg for msg in compressed_messages 
                if isinstance(msg, ToolMessage) and hasattr(msg, 'tool_call_id')
            ]
            found_ids = {msg.tool_call_id for msg in tool_messages if msg.tool_call_id in tool_call_ids}
            assert found_ids == tool_call_ids, "Incomplete tool call pairs found"

        # Verify we're within token limit
        assert limited_cm.count_tokens(compressed_messages) <= 60  # Allow small overhead

    def test_compress_messages_preserves_aimessage_toolmessage_across_prefix_suffix(self):
        """Test that compression preserves AIMessage-ToolMessage pairs when they span prefix/suffix boundary"""
        # Create a context manager that preserves 3 messages in prefix
        limited_cm = ContextManager(
            token_limit=300, preserve_prefix_message_count=3, model_name=TEST_MODEL
        )

        # Create an AIMessage with tool_calls that will be in the prefix
        ai_message_with_tools = AIMessage(
            content="Searching...",
            tool_calls=[
                {"name": "web_search", "args": {"query": "test 1"}, "id": "call_1", "type": "tool_call"},
                {"name": "web_search", "args": {"query": "test 2"}, "id": "call_2", "type": "tool_call"},
                {"name": "web_search", "args": {"query": "test 3"}, "id": "call_3", "type": "tool_call"},
            ]
        )

        messages = [
            HumanMessage(content="Hello"),
            HumanMessage(content="More context"),
            ai_message_with_tools,  # This will be in prefix (position 3)
            # These ToolMessages will be after the prefix
            ToolMessage(content="Result 1 " * 50, tool_call_id="call_1"),
            ToolMessage(content="Result 2 " * 50, tool_call_id="call_2"),
            ToolMessage(content="Result 3 " * 50, tool_call_id="call_3"),
            HumanMessage(content="What about this?"),
        ]

        compressed = limited_cm.compress_messages({"messages": messages})
        compressed_messages = compressed["messages"]

        # Verify: If AIMessage with tool_calls is present, ALL its ToolMessages must be present
        ai_messages_with_tools = [
            msg for msg in compressed_messages 
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls
        ]

        for ai_msg in ai_messages_with_tools:
            # Extract tool call IDs
            tool_call_ids = set()
            for tc in ai_msg.tool_calls:
                if isinstance(tc, dict) and 'id' in tc:
                    tool_call_ids.add(tc['id'])
                elif hasattr(tc, 'id'):
                    tool_call_ids.add(tc.id)

            # Find all ToolMessages in compressed messages
            tool_messages = [
                msg for msg in compressed_messages 
                if isinstance(msg, ToolMessage)
            ]

            # Count how many of our tool_calls have corresponding ToolMessages
            found_tool_call_ids = set()
            for tool_msg in tool_messages:
                if hasattr(tool_msg, 'tool_call_id') and tool_msg.tool_call_id in tool_call_ids:
                    found_tool_call_ids.add(tool_msg.tool_call_id)

            # All tool_calls must have their ToolMessages
            assert found_tool_call_ids == tool_call_ids, (
                f"AIMessage with tool_calls in prefix but not all ToolMessages found. "
                f"Expected: {tool_call_ids}, Found: {found_tool_call_ids}"
            )

        # Verify total tokens are within limit (with small overhead allowance)
        assert limited_cm.count_tokens(compressed_messages) <= 310

    def test_compress_messages_removes_orphaned_toolmessages_when_aimessage_excluded(self):
        """Test that ToolMessages are removed when their AIMessage is excluded due to space constraints"""
        # Create a very small token limit
        limited_cm = ContextManager(
            token_limit=100, preserve_prefix_message_count=3, model_name=TEST_MODEL
        )

        # Create an AIMessage with tool_calls that will be in prefix but can't fit with all ToolMessages
        ai_message_with_tools = AIMessage(
            content="Searching...",
            tool_calls=[
                {"name": "web_search", "args": {"query": "test"}, "id": "call_1", "type": "tool_call"},
                {"name": "web_search", "args": {"query": "test"}, "id": "call_2", "type": "tool_call"},
            ]
        )

        messages = [
            HumanMessage(content="Hi"),
            HumanMessage(content="Q"),
            ai_message_with_tools,  # This will be in prefix position 3
            # These large ToolMessages won't fit with the AIMessage
            ToolMessage(content="Large result " * 100, tool_call_id="call_1"),
            ToolMessage(content="Large result " * 100, tool_call_id="call_2"),
            HumanMessage(content="Final"),
        ]

        compressed = limited_cm.compress_messages({"messages": messages})
        compressed_messages = compressed["messages"]

        # The AIMessage should be removed because ToolMessages don't fit
        ai_messages_with_tools = [
            msg for msg in compressed_messages 
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls
        ]
        
        # No AIMessage with tool_calls should be present (it was removed)
        # OR if present, all its ToolMessages must be present
        for ai_msg in ai_messages_with_tools:
            tool_call_ids = {tc.get('id') if isinstance(tc, dict) else tc.id for tc in ai_msg.tool_calls}
            tool_messages = [
                msg for msg in compressed_messages 
                if isinstance(msg, ToolMessage) and hasattr(msg, 'tool_call_id')
            ]
            found_ids = {msg.tool_call_id for msg in tool_messages if msg.tool_call_id in tool_call_ids}
            assert found_ids == tool_call_ids, "Incomplete tool call pairs found"

        # More importantly: verify NO orphaned ToolMessages exist
        # (ToolMessages whose AIMessage was removed)
        all_ai_tool_call_ids = set()
        for msg in compressed_messages:
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_id = tc.get('id') if isinstance(tc, dict) else tc.id
                    if tc_id:
                        all_ai_tool_call_ids.add(tc_id)
        
        # Check all ToolMessages have their AIMessage present
        for msg in compressed_messages:
            if isinstance(msg, ToolMessage) and hasattr(msg, 'tool_call_id'):
                assert msg.tool_call_id in all_ai_tool_call_ids, (
                    f"Orphaned ToolMessage found with call_id {msg.tool_call_id} - "
                    f"its AIMessage was removed but the ToolMessage was not"
                )

        # Verify we're within token limit
        assert limited_cm.count_tokens(compressed_messages) <= 110
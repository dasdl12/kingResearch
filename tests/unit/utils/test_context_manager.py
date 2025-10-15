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

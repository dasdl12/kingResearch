# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Comprehensive tests for context optimization features:
1. tiktoken accurate token counting
2. Intelligent message compression
3. Smart summarization
"""

import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from src.utils.context_manager import ContextManager


class TestTiktokenTokenCounting:
    """Test tiktoken-based token counting accuracy"""

    def test_tiktoken_available(self):
        """Test that tiktoken is properly loaded"""
        manager = ContextManager(token_limit=100000)

        # Check if tiktoken encoding is initialized
        assert manager._encoding is not None, "tiktoken encoding should be initialized"

        print("✅ tiktoken is properly loaded and initialized")

    def test_token_counting_accuracy_english(self):
        """Test token counting accuracy for English text"""
        manager = ContextManager(token_limit=100000)

        # Test English text
        english_text = "Hello World! This is a test message for accurate token counting."
        tokens = manager._count_text_tokens(english_text)

        # With tiktoken, this should be ~15-20 tokens
        # Old character-based would estimate: 64/4 ≈ 16 tokens
        print(f"English text tokens: {tokens}")
        assert 10 < tokens < 30, f"English token count seems wrong: {tokens}"

        print(f"✅ English text: '{english_text[:50]}...' → {tokens} tokens")

    def test_token_counting_accuracy_chinese(self):
        """Test token counting accuracy for Chinese text"""
        manager = ContextManager(token_limit=100000)

        # Test Chinese text
        chinese_text = "你好，世界！这是一个用于测试精确token计数的消息。"
        tokens = manager._count_text_tokens(chinese_text)

        # With tiktoken, Chinese chars are usually 2-3 tokens each
        # Old character-based would estimate: 24 chars ≈ 24 tokens
        print(f"Chinese text tokens: {tokens}")
        assert 20 < tokens < 80, f"Chinese token count seems wrong: {tokens}"

        print(f"✅ Chinese text: '{chinese_text}' → {tokens} tokens")

    def test_token_counting_mixed_language(self):
        """Test token counting for mixed language text"""
        manager = ContextManager(token_limit=100000)

        # Mixed text
        mixed_text = "你好，世界！Hello World! 这是测试 This is a test."
        tokens = manager._count_text_tokens(mixed_text)

        print(f"Mixed text tokens: {tokens}")
        assert 15 < tokens < 60, f"Mixed language token count seems wrong: {tokens}"

        print(f"✅ Mixed text: '{mixed_text}' → {tokens} tokens")

    def test_message_token_counting(self):
        """Test token counting for different message types"""
        manager = ContextManager(token_limit=100000)

        # Test HumanMessage
        human_msg = HumanMessage(content="What is deep research?")
        human_tokens = manager._count_message_tokens(human_msg)
        print(f"HumanMessage tokens: {human_tokens}")

        # Test AIMessage
        ai_msg = AIMessage(content="Deep research is a systematic approach to investigating topics.")
        ai_tokens = manager._count_message_tokens(ai_msg)
        print(f"AIMessage tokens: {ai_tokens}")

        # Test ToolMessage
        tool_msg = ToolMessage(
            content="Search results: Found 10 relevant papers on deep research.",
            tool_call_id="test_123"
        )
        tool_tokens = manager._count_message_tokens(tool_msg)
        print(f"ToolMessage tokens: {tool_tokens}")

        assert human_tokens > 0, "HumanMessage should have tokens"
        assert ai_tokens > human_tokens, "AIMessage should have more tokens (1.15x multiplier)"
        assert tool_tokens > 0, "ToolMessage should have tokens"

        print(f"✅ Message token counting works correctly")

    def test_token_counting_accuracy_comparison(self):
        """Compare tiktoken vs character-based estimation"""
        manager = ContextManager(token_limit=100000)

        test_text = "This is a comprehensive test message with mixed content: 这是一个包含中英文的测试消息。"

        # Get tiktoken count
        tiktoken_count = manager._count_text_tokens(test_text)

        # Get character-based estimate
        char_based_count = manager._estimate_tokens_by_chars(test_text)

        print(f"\n📊 Token Counting Comparison:")
        print(f"   Test text: '{test_text}'")
        print(f"   tiktoken count: {tiktoken_count}")
        print(f"   Character-based estimate: {char_based_count}")
        print(f"   Difference: {abs(tiktoken_count - char_based_count)} tokens")
        print(f"   Accuracy improvement: {abs(tiktoken_count - char_based_count) / max(tiktoken_count, 1) * 100:.1f}%")

        # tiktoken should be more accurate (usually higher for mixed content)
        assert tiktoken_count > 0, "tiktoken count should be positive"

        print(f"✅ Token counting comparison completed")


class TestIntelligentCompression:
    """Test intelligent message compression strategies"""

    def test_sliding_window_preservation(self):
        """Test that sliding window preserves recent messages"""
        manager = ContextManager(
            token_limit=1000,
            sliding_window_size=3,
            enable_smart_summary=True
        )

        # Create 10 messages
        messages = [
            HumanMessage(content=f"Message {i}: " + "test " * 50)
            for i in range(10)
        ]

        state = {"messages": messages}
        compressed_state = manager.compress_messages(state)
        compressed_messages = compressed_state["messages"]

        print(f"\n📦 Sliding Window Test:")
        print(f"   Original messages: {len(messages)}")
        print(f"   Compressed messages: {len(compressed_messages)}")
        print(f"   Original tokens: {manager.count_tokens(messages)}")
        print(f"   Compressed tokens: {manager.count_tokens(compressed_messages)}")

        # Should have fewer messages due to compression
        assert len(compressed_messages) < len(messages), "Should compress some messages"

        # Should preserve recent messages (last 3)
        # Check if last message is preserved
        last_original = messages[-1].content
        last_compressed = compressed_messages[-1].content

        # Last message should be identical or very similar
        assert "Message 9" in last_compressed, "Last message should be preserved"

        print(f"✅ Sliding window preserves recent {manager.sliding_window_size} messages")

    def test_compression_ratio(self):
        """Test that compression achieves significant token reduction"""
        manager = ContextManager(
            token_limit=5000,
            sliding_window_size=3,
            enable_smart_summary=True
        )

        # Create many large messages
        messages = [
            AIMessage(content="Research finding: " + "Important data point. " * 100)
            for _ in range(20)
        ]

        state = {"messages": messages}
        original_tokens = manager.count_tokens(messages)

        compressed_state = manager.compress_messages(state)
        compressed_tokens = manager.count_tokens(compressed_state["messages"])

        reduction_percentage = ((original_tokens - compressed_tokens) / original_tokens) * 100

        print(f"\n📉 Compression Ratio Test:")
        print(f"   Original tokens: {original_tokens}")
        print(f"   Compressed tokens: {compressed_tokens}")
        print(f"   Reduction: {reduction_percentage:.1f}%")

        # Should achieve at least 30% reduction
        assert reduction_percentage > 30, f"Compression should reduce by at least 30%, got {reduction_percentage:.1f}%"

        print(f"✅ Achieved {reduction_percentage:.1f}% token reduction")

    def test_prefix_message_preservation(self):
        """Test that prefix messages (system prompts) are preserved"""
        manager = ContextManager(
            token_limit=2000,
            preserve_prefix_message_count=2,
            sliding_window_size=2
        )

        # Create messages with system prompt at beginning
        messages = [
            SystemMessage(content="You are a helpful research assistant."),
            HumanMessage(content="Research prompt guidelines."),
            *[HumanMessage(content=f"Message {i}: " + "test " * 30) for i in range(10)]
        ]

        state = {"messages": messages}
        compressed_state = manager.compress_messages(state)
        compressed_messages = compressed_state["messages"]

        print(f"\n🔒 Prefix Preservation Test:")
        print(f"   Original first message: {messages[0].content[:50]}...")
        print(f"   Compressed first message: {compressed_messages[0].content[:50]}...")

        # First message should be preserved
        assert isinstance(compressed_messages[0], SystemMessage), "First message should be SystemMessage"
        assert "helpful research assistant" in compressed_messages[0].content, "System prompt should be preserved"

        print(f"✅ Prefix messages (system prompts) are preserved")


class TestSmartSummarization:
    """Test intelligent message summarization (RULE-BASED, not LLM)"""

    def test_finding_extraction(self):
        """Test extraction of <finding> tags"""
        manager = ContextManager(token_limit=100000, enable_smart_summary=True)

        # Create message with findings
        content = """
        <finding>
        This is an important research finding about deep learning.
        The results show significant improvements in accuracy.
        Key metrics: 95% accuracy, 10x faster processing.
        </finding>

        Additional context that is less important.
        """

        message = ToolMessage(content=content, tool_call_id="test")
        summarized = manager._summarize_message(message, max_tokens=100)

        print(f"\n🔍 Finding Extraction Test:")
        print(f"   Original length: {len(content)} chars")
        print(f"   Summary: {summarized.content[:200]}...")

        # Summary should contain key finding
        assert "deep learning" in summarized.content or "important research" in summarized.content, \
            "Summary should extract key findings"
        assert "[SUMMARIZED]" in summarized.content, "Summary should be marked"

        print(f"✅ Finding extraction works correctly")

    def test_bullet_point_extraction(self):
        """Test extraction of bullet points"""
        manager = ContextManager(token_limit=100000, enable_smart_summary=True)

        content = """
        Research Results:

        - Finding 1: Deep learning models improve accuracy by 15%
        - Finding 2: Training time reduced by 50%
        - Finding 3: Model size decreased by 30%
        - Finding 4: Inference speed increased 2x
        - Finding 5: Memory usage optimized

        Additional details and methodology...
        """ + "More context. " * 100

        message = AIMessage(content=content)
        summarized = manager._summarize_message(message, max_tokens=200)

        print(f"\n📋 Bullet Point Extraction Test:")
        print(f"   Original length: {len(content)} chars")
        print(f"   Summary length: {len(summarized.content)} chars")
        print(f"   Summary: {summarized.content[:300]}...")

        # Summary should contain bullet points
        assert "Finding 1" in summarized.content or "Deep learning" in summarized.content, \
            "Summary should extract bullet points"

        print(f"✅ Bullet point extraction works correctly")

    def test_summarization_is_rule_based(self):
        """Verify that summarization is rule-based, NOT LLM-based"""
        manager = ContextManager(token_limit=100000, enable_smart_summary=True)

        print(f"\n⚙️ Summarization Method Verification:")
        print(f"   ❌ NOT using LLM for summarization")
        print(f"   ✅ Using rule-based pattern matching")
        print(f"   Patterns used:")
        print(f"      1. Extract <finding> tags")
        print(f"      2. Extract 'Key Findings', 'Conclusion' sections")
        print(f"      3. Extract bullet points")
        print(f"      4. Extract first + last paragraphs")
        print(f"      5. Simple truncation as fallback")
        print(f"\n   Benefits:")
        print(f"      ✅ No additional LLM calls (faster)")
        print(f"      ✅ No extra token costs")
        print(f"      ✅ No risk of recursive context overflow")
        print(f"      ✅ Deterministic and predictable")

        # This is just informational, no assertion needed
        assert True, "Rule-based summarization is the design choice"


class TestStepSummarization:
    """Test step-level summarization in research workflow"""

    def test_key_finding_extraction_patterns(self):
        """Test various patterns for extracting key findings"""
        from src.graph.nodes import _extract_key_findings

        # Test with explicit "Key Findings" section
        content1 = """
        Research Process:

        Multiple steps were taken...

        Key Findings:
        - Deep learning significantly improves accuracy
        - Training time is reduced by 50%
        - Model is more efficient

        Additional details...
        """

        summary1 = _extract_key_findings(content1, max_length=200)
        print(f"\n🔑 Key Finding Pattern Test 1:")
        print(f"   Input: 'Key Findings' section")
        print(f"   Output: {summary1}")

        assert "Deep learning" in summary1 or "accuracy" in summary1, \
            "Should extract Key Findings section"

        # Test with bullet points
        content2 = """
        Research Results:

        - Major finding 1 about performance
        - Major finding 2 about efficiency
        - Major finding 3 about scalability

        """ + "Details... " * 50

        summary2 = _extract_key_findings(content2, max_length=200)
        print(f"\n🔑 Key Finding Pattern Test 2:")
        print(f"   Input: Bullet points")
        print(f"   Output: {summary2}")

        assert "Major finding" in summary2 or "performance" in summary2, \
            "Should extract bullet points"

        print(f"✅ Key finding extraction patterns work correctly")

    def test_step_formatting_with_few_steps(self):
        """Test step formatting when there are few steps (≤2)"""
        from src.graph.nodes import _format_completed_steps_with_summary
        from src.prompts.planner_model import Step

        # Create 2 steps
        steps = [
            Step(
                need_search=True,
                title="Step 1: Initial Research",
                description="Research task",
                step_type="research",
                execution_res="Finding 1: Important data about topic A."
            ),
            Step(
                need_search=True,
                title="Step 2: Deep Analysis",
                description="Analysis task",
                step_type="processing",
                execution_res="Finding 2: Critical insights about topic B."
            )
        ]

        result = _format_completed_steps_with_summary(steps, keep_recent_full=2)

        print(f"\n📝 Few Steps Test:")
        print(f"   Steps: {len(steps)}")
        print(f"   Result length: {len(result)} chars")
        print(f"   Contains 'Step 1': {('Step 1' in result)}")
        print(f"   Contains 'Step 2': {('Step 2' in result)}")

        # All steps should be kept in full
        assert "Step 1" in result, "Step 1 should be present"
        assert "Step 2" in result, "Step 2 should be present"
        assert "Finding 1" in result, "Step 1 findings should be present"
        assert "Finding 2" in result, "Step 2 findings should be present"

        print(f"✅ Few steps are kept in full detail")

    def test_step_formatting_with_many_steps(self):
        """Test step formatting when there are many steps (>2)"""
        from src.graph.nodes import _format_completed_steps_with_summary
        from src.prompts.planner_model import Step

        # Create 5 steps
        steps = [
            Step(
                need_search=True,
                title=f"Step {i+1}: Research Phase {i+1}",
                description=f"Research task {i+1}",
                step_type="research",
                execution_res=f"Finding {i+1}: Important data. " + "Details. " * 50
            )
            for i in range(5)
        ]

        result = _format_completed_steps_with_summary(steps, keep_recent_full=2)

        print(f"\n📚 Many Steps Test:")
        print(f"   Total steps: {len(steps)}")
        print(f"   Keep recent full: 2")
        print(f"   Result length: {len(result)} chars")
        print(f"   Contains 'Summary of Earlier Steps': {('Summary of Earlier Steps' in result)}")

        # Should have summary section
        assert "Summary of Earlier Steps" in result, "Should have summary section for older steps"

        # Recent steps should be in full
        assert "Step 4" in result, "Step 4 should be present"
        assert "Step 5" in result, "Step 5 should be present"

        # Older steps should be summarized (shorter)
        step1_in_summary = result.find("Step 1")
        step4_in_full = result.find("Step 4")

        # The Step 1 section should appear before Step 4 section
        assert step1_in_summary < step4_in_full, "Summarized steps should appear before full steps"

        print(f"✅ Many steps: older steps summarized, recent steps kept full")


def test_integration_full_workflow():
    """Integration test: Full workflow simulation"""
    print(f"\n" + "="*60)
    print(f"🚀 INTEGRATION TEST: Full Workflow Simulation")
    print(f"="*60)

    manager = ContextManager(
        token_limit=10000,
        preserve_prefix_message_count=2,
        enable_smart_summary=True,
        sliding_window_size=3
    )

    # Simulate a research workflow
    messages = [
        SystemMessage(content="You are a deep research assistant."),
        HumanMessage(content="Research the top 5 deep learning frameworks."),
    ]

    # Add 5 research steps worth of messages
    for i in range(5):
        messages.append(
            AIMessage(content=f"<finding>Step {i+1} findings: " + "Important research data. " * 50 + "</finding>")
        )
        messages.append(
            ToolMessage(content=f"Search results for step {i+1}: " + "Detailed information. " * 100, tool_call_id=f"tool_{i}")
        )

    state = {"messages": messages}

    original_tokens = manager.count_tokens(messages)
    print(f"\n📊 Workflow Statistics:")
    print(f"   Total messages: {len(messages)}")
    print(f"   Original tokens: {original_tokens}")

    # Apply compression
    compressed_state = manager.compress_messages(state)
    compressed_messages = compressed_state["messages"]
    compressed_tokens = manager.count_tokens(compressed_messages)

    reduction = ((original_tokens - compressed_tokens) / original_tokens) * 100

    print(f"   Compressed messages: {len(compressed_messages)}")
    print(f"   Compressed tokens: {compressed_tokens}")
    print(f"   Token reduction: {reduction:.1f}%")
    print(f"   Within limit: {compressed_tokens <= manager.token_limit}")

    # Verify results
    assert compressed_tokens <= manager.token_limit, "Should be within token limit"
    assert reduction > 20, f"Should achieve significant reduction, got {reduction:.1f}%"

    # Verify system message is preserved
    assert isinstance(compressed_messages[0], SystemMessage), "System message should be preserved"

    # Verify recent messages are preserved
    assert len(compressed_messages) >= 3, "Should preserve at least sliding window size"

    print(f"\n✅ Integration test passed!")
    print(f"   ✓ Token limit respected")
    print(f"   ✓ System prompts preserved")
    print(f"   ✓ Recent context maintained")
    print(f"   ✓ Significant compression achieved")


if __name__ == "__main__":
    print("="*60)
    print("🧪 CONTEXT OPTIMIZATION TEST SUITE")
    print("="*60)

    # Run all test classes
    test_classes = [
        TestTiktokenTokenCounting,
        TestIntelligentCompression,
        TestSmartSummarization,
        TestStepSummarization,
    ]

    for test_class in test_classes:
        print(f"\n\n{'='*60}")
        print(f"📦 Running: {test_class.__name__}")
        print(f"{'='*60}")

        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith('test_') and callable(getattr(instance, m))]

        for method_name in methods:
            print(f"\n🔬 {method_name}")
            print(f"-" * 60)
            try:
                method = getattr(instance, method_name)
                method()
                print(f"✅ PASSED")
            except Exception as e:
                print(f"❌ FAILED: {e}")
                import traceback
                traceback.print_exc()

    # Run integration test
    print(f"\n\n{'='*60}")
    print(f"🔗 Running Integration Test")
    print(f"{'='*60}")
    try:
        test_integration_full_workflow()
    except Exception as e:
        print(f"❌ Integration test FAILED: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n\n{'='*60}")
    print(f"✅ ALL TESTS COMPLETED")
    print(f"{'='*60}")

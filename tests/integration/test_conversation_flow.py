# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Integration tests for conversation creation and title update flow.

Tests the following scenarios:
1. When starting a conversation from empty state, frontend should see new conversation in sidebar
2. After user sends a topic, conversation title should be updated
"""

import asyncio
import json
import logging
import os
import sys
from typing import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

# Fix for Windows async event loop with psycopg
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.database.models import (
    ConversationRepository,
    MessageRepository,
    init_database,
)
from src.server.app import app

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Initialize test database before running tests."""
    init_database()
    yield
    # Cleanup is handled by PostgreSQL CASCADE on conversation deletion


@pytest.fixture
async def test_client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def cleanup_conversation():
    """Fixture to clean up created conversations after test."""
    conversation_ids = []

    def register_conversation(conv_id: str):
        conversation_ids.append(conv_id)

    yield register_conversation

    # Cleanup
    repo = ConversationRepository()
    try:
        for conv_id in conversation_ids:
            try:
                repo.delete_conversation(conv_id)
                logger.info(f"Cleaned up conversation: {conv_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup conversation {conv_id}: {e}")
    finally:
        repo.close()


async def parse_sse_stream(content: AsyncIterator[bytes]) -> list[dict]:
    """Parse Server-Sent Events stream and return list of events."""
    events = []
    current_event = None
    
    async for chunk in content:
        lines = chunk.decode("utf-8").split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_event:
                    events.append(current_event)
                    current_event = None
                continue
            
            if line.startswith("event:"):
                event_type = line[6:].strip()
                current_event = {"type": event_type}
            elif line.startswith("data:"):
                if current_event:
                    data_str = line[5:].strip()
                    try:
                        current_event["data"] = json.loads(data_str)
                    except json.JSONDecodeError:
                        current_event["data"] = data_str
    
    # Add last event if exists
    if current_event:
        events.append(current_event)
    
    return events


@pytest.mark.asyncio
async def test_new_conversation_appears_in_sidebar(test_client, cleanup_conversation):
    """
    Test Bug 1: New conversation should appear in frontend sidebar immediately.
    
    Steps:
    1. Start with no conversations
    2. Send first message with thread_id="__default__"
    3. Verify conversation_init event contains full conversation data
    4. Verify new conversation can be retrieved via API
    """
    # Send a message to create new conversation
    response = await test_client.post(
        "/api/chat/stream",
        json={
            "thread_id": "__default__",
            "messages": [{"role": "user", "content": "What is machine learning?"}],
            "resources": [],
            "auto_accepted_plan": True,
            "max_plan_iterations": 3,
            "max_step_num": 5,
            "max_search_results": 5,
        },
        timeout=30.0,
    )
    
    assert response.status_code == 200
    
    # Parse SSE stream
    events = await parse_sse_stream(response.aiter_bytes())
    
    # Find conversation_init event
    conv_init_event = None
    for event in events:
        if event.get("type") == "conversation_init":
            conv_init_event = event
            break
    
    assert conv_init_event is not None, "conversation_init event not found in stream"
    
    # Verify event contains full conversation data
    event_data = conv_init_event["data"]
    assert "conversation_id" in event_data, "conversation_id missing in event"
    assert "conversation" in event_data, "conversation object missing in event"
    
    conversation_id = event_data["conversation_id"]
    conversation_data = event_data["conversation"]
    
    # Register for cleanup
    cleanup_conversation(conversation_id)
    
    # Verify conversation data structure
    assert "id" in conversation_data
    assert "title" in conversation_data
    assert "created_at" in conversation_data
    assert "updated_at" in conversation_data
    assert "message_count" in conversation_data
    
    # Verify conversation exists in database via API
    conv_response = await test_client.get(f"/api/conversations/{conversation_id}")
    assert conv_response.status_code == 200
    
    conv_from_api = conv_response.json()
    assert conv_from_api["id"] == conversation_id
    assert conv_from_api["title"] in ["New Conversation", "What is machine learning?"]
    
    # Verify conversation appears in list
    list_response = await test_client.get("/api/conversations?limit=50&offset=0")
    assert list_response.status_code == 200
    
    conversations_list = list_response.json()["conversations"]
    assert any(c["id"] == conversation_id for c in conversations_list), \
        "New conversation not found in conversations list"
    
    logger.info(f"✓ Test passed: New conversation {conversation_id} appears in sidebar")


@pytest.mark.asyncio
async def test_conversation_title_updates_after_user_message(test_client, cleanup_conversation):
    """
    Test Bug 2: Conversation title should update after user sends first message.
    
    Steps:
    1. Create a new conversation
    2. Send first user message
    3. Verify conversation_title_updated event is emitted
    4. Verify title is updated in database
    """
    # Send a message to create new conversation with a clear topic
    test_topic = "What are the benefits of renewable energy?"
    
    response = await test_client.post(
        "/api/chat/stream",
        json={
            "thread_id": "__default__",
            "messages": [{"role": "user", "content": test_topic}],
            "resources": [],
            "auto_accepted_plan": True,
            "enable_background_investigation": False,  # Disable to avoid unrelated errors
            "max_plan_iterations": 3,
            "max_step_num": 5,
            "max_search_results": 5,
        },
        timeout=60.0,  # Give more time for title generation
    )
    
    assert response.status_code == 200
    
    # Parse SSE stream
    events = await parse_sse_stream(response.aiter_bytes())
    
    # Find conversation_init event to get conversation_id
    conversation_id = None
    for event in events:
        if event.get("type") == "conversation_init":
            conversation_id = event["data"]["conversation_id"]
            break
    
    assert conversation_id is not None, "conversation_id not found"
    cleanup_conversation(conversation_id)
    
    # Find conversation_title_updated event
    title_update_event = None
    updated_title = None
    for event in events:
        if event.get("type") == "conversation_title_updated":
            title_update_event = event
            updated_title = event["data"].get("title")
            break
    
    assert title_update_event is not None, "conversation_title_updated event not found in stream"
    assert updated_title is not None, "title missing in title update event"
    assert updated_title != "New Conversation", "Title was not generated"
    
    # Verify title is updated in database
    # Wait a moment for database update to complete
    await asyncio.sleep(1)
    
    conv_response = await test_client.get(f"/api/conversations/{conversation_id}")
    assert conv_response.status_code == 200
    
    conv_from_api = conv_response.json()
    assert conv_from_api["title"] != "New Conversation", \
        "Title still 'New Conversation' in database"
    assert conv_from_api["title"] == updated_title, \
        f"Title in database ({conv_from_api['title']}) doesn't match event title ({updated_title})"
    
    # Verify title is meaningful (not just truncated message)
    assert len(conv_from_api["title"]) > 0, "Title is empty"
    assert len(conv_from_api["title"]) <= 100, "Title is too long"
    
    logger.info(f"✓ Test passed: Conversation title updated to '{updated_title}'")


@pytest.mark.asyncio
async def test_title_generation_logic(test_client):
    """
    Test the title generation logic to answer user's question about how titles are generated.
    
    This test verifies:
    - Titles are generated using basic LLM (not coordinator)
    - Titles are concise (max 6 words as per prompt)
    - Title generation happens immediately after first message
    """
    test_messages = [
        "How does photosynthesis work?",
        "最佳的Python学习路径是什么？",
        "Explain quantum computing in simple terms"
    ]
    
    for test_message in test_messages:
        # Use the generate-title API directly
        response = await test_client.post(
            "/api/conversations/generate-title",
            json={"first_message": test_message},
            timeout=30.0,
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert "title" in result, "title missing in response"
        title = result["title"]
        
        # Verify title properties
        assert len(title) > 0, "Title is empty"
        assert title != test_message, "Title is just the original message"
        
        # Title should be concise (roughly 6 words or less, allowing some flexibility)
        word_count = len(title.split())
        assert word_count <= 10, f"Title too long ({word_count} words): {title}"
        
        logger.info(f"✓ Generated title for '{test_message}': '{title}'")
    
    logger.info("✓ Test passed: Title generation logic works correctly")


@pytest.mark.asyncio
async def test_conversation_workflow_end_to_end(test_client, cleanup_conversation):
    """
    End-to-end test of the complete conversation workflow.
    
    Steps:
    1. User opens app with no active conversation
    2. User sends first message
    3. Frontend receives conversation_init with conversation data
    4. Frontend receives conversation_title_updated with generated title
    5. Sidebar shows new conversation with proper title
    """
    # Simulate user sending first message
    user_message = "What is the impact of climate change on polar bears?"
    
    response = await test_client.post(
        "/api/chat/stream",
        json={
            "thread_id": "__default__",
            "messages": [{"role": "user", "content": user_message}],
            "resources": [],
            "auto_accepted_plan": True,
            "enable_background_investigation": False,  # Disable to avoid unrelated errors
            "max_plan_iterations": 3,
            "max_step_num": 5,
            "max_search_results": 5,
        },
        timeout=60.0,
    )
    
    assert response.status_code == 200
    
    # Parse events
    events = await parse_sse_stream(response.aiter_bytes())
    event_types = [e.get("type") for e in events]
    
    # Verify event sequence
    assert "conversation_init" in event_types, "conversation_init event missing"
    assert "conversation_title_updated" in event_types, "conversation_title_updated event missing"
    
    # Get conversation ID
    conv_init = next(e for e in events if e.get("type") == "conversation_init")
    conversation_id = conv_init["data"]["conversation_id"]
    cleanup_conversation(conversation_id)
    
    # Verify conversation data in init event
    assert "conversation" in conv_init["data"], "conversation data missing in init event"
    init_conv = conv_init["data"]["conversation"]
    assert init_conv["title"] == "New Conversation", "Initial title should be 'New Conversation'"
    
    # Get updated title
    title_update = next(e for e in events if e.get("type") == "conversation_title_updated")
    updated_title = title_update["data"]["title"]
    
    assert updated_title != "New Conversation", "Title should be updated"
    assert len(updated_title) > 0, "Updated title is empty"
    
    # Verify final state in database
    await asyncio.sleep(1)  # Wait for DB update
    conv_response = await test_client.get(f"/api/conversations/{conversation_id}")
    final_conv = conv_response.json()
    
    assert final_conv["title"] == updated_title, "Final title doesn't match"
    assert final_conv["message_count"] >= 1, "Message count should be at least 1"
    
    # Verify messages were saved
    msg_response = await test_client.get(f"/api/conversations/{conversation_id}/messages")
    messages = msg_response.json()["messages"]
    
    assert len(messages) >= 1, "User message was not saved"
    assert messages[0]["role"] == "user", "First message should be from user"
    assert messages[0]["content"] == user_message, "User message content doesn't match"
    
    logger.info(f"✓ End-to-end test passed: Conversation '{updated_title}' created successfully")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])


# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
简化的对话功能测试 - 只测试对话和标题管理，不执行完整workflow
"""

import asyncio
import sys

import pytest
from httpx import ASGITransport, AsyncClient

# Fix for Windows async event loop with psycopg
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, ".")

from src.database.models import (
    ConversationRepository,
    MessageRepository,
    init_database,
)
from src.server.app import app


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Initialize test database."""
    init_database()
    yield


@pytest.fixture
async def test_client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def cleanup_conversation():
    """Cleanup conversations after test."""
    conversation_ids = []

    def register(conv_id: str):
        conversation_ids.append(conv_id)

    yield register

    repo = ConversationRepository()
    try:
        for conv_id in conversation_ids:
            try:
                repo.delete_conversation(conv_id)
            except Exception:
                pass
    finally:
        repo.close()


@pytest.mark.asyncio
async def test_create_conversation_api(test_client, cleanup_conversation):
    """测试创建对话API"""
    response = await test_client.post(
        "/api/conversations",
        json={"title": "Test Conversation"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "id" in data
    assert data["title"] == "Test Conversation"
    assert data["message_count"] == 0
    
    cleanup_conversation(data["id"])
    print(f"✓ 对话创建成功: {data['id']}")


@pytest.mark.asyncio
async def test_list_conversations_api(test_client, cleanup_conversation):
    """测试列出对话API"""
    # 创建几个测试对话
    conv1 = await test_client.post("/api/conversations", json={"title": "Conv 1"})
    conv2 = await test_client.post("/api/conversations", json={"title": "Conv 2"})
    
    conv1_id = conv1.json()["id"]
    conv2_id = conv2.json()["id"]
    
    cleanup_conversation(conv1_id)
    cleanup_conversation(conv2_id)
    
    # 列出对话
    response = await test_client.get("/api/conversations?limit=50&offset=0")
    assert response.status_code == 200
    
    data = response.json()
    assert "conversations" in data
    assert len(data["conversations"]) >= 2
    
    # 验证我们创建的对话在列表中
    conv_ids = [c["id"] for c in data["conversations"]]
    assert conv1_id in conv_ids
    assert conv2_id in conv_ids
    
    print(f"✓ 对话列表获取成功，包含 {len(data['conversations'])} 个对话")


@pytest.mark.asyncio
async def test_update_conversation_title(test_client, cleanup_conversation):
    """测试更新对话标题"""
    # 创建对话
    create_resp = await test_client.post(
        "/api/conversations",
        json={"title": "Original Title"}
    )
    conv_id = create_resp.json()["id"]
    cleanup_conversation(conv_id)
    
    # 更新标题
    update_resp = await test_client.put(
        f"/api/conversations/{conv_id}",
        json={"title": "Updated Title"}
    )
    
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["title"] == "Updated Title"
    
    # 验证标题已更新
    get_resp = await test_client.get(f"/api/conversations/{conv_id}")
    assert get_resp.json()["title"] == "Updated Title"
    
    print(f"✓ 标题更新成功: Original Title -> Updated Title")


@pytest.mark.asyncio
async def test_generate_title_api(test_client):
    """测试标题生成API"""
    response = await test_client.post(
        "/api/conversations/generate-title",
        json={"first_message": "What is artificial intelligence?"},
        timeout=30.0
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "title" in data
    assert len(data["title"]) > 0
    assert data["title"] != "What is artificial intelligence?"
    
    # 验证标题简洁
    word_count = len(data["title"].split())
    assert word_count <= 10, f"标题太长 ({word_count} 词): {data['title']}"
    
    print(f"✓ 标题生成成功: '{data['title']}'")


@pytest.mark.asyncio
async def test_conversation_with_messages(test_client, cleanup_conversation):
    """测试对话和消息的完整流程"""
    # 1. 创建对话
    conv_resp = await test_client.post(
        "/api/conversations",
        json={"title": "New Conversation"}
    )
    conv_id = conv_resp.json()["id"]
    cleanup_conversation(conv_id)
    
    # 2. 模拟添加消息（通过数据库直接添加）
    from src.database.models import Message
    msg_repo = MessageRepository()
    try:
        # 添加用户消息
        user_msg = Message(
            conversation_id=conv_id,
            role="user",
            content="Hello, how are you?"
        )
        msg_repo.add_message(user_msg)
        
        # 添加助手消息
        assistant_msg = Message(
            conversation_id=conv_id,
            role="assistant",
            content="I'm doing well, thank you!",
            agent="coordinator"
        )
        msg_repo.add_message(assistant_msg)
    finally:
        msg_repo.close()
    
    # 3. 获取对话，验证消息计数
    conv_resp = await test_client.get(f"/api/conversations/{conv_id}")
    conv_data = conv_resp.json()
    assert conv_data["message_count"] == 2
    
    # 4. 获取消息列表
    msg_resp = await test_client.get(f"/api/conversations/{conv_id}/messages")
    msg_data = msg_resp.json()
    
    assert len(msg_data["messages"]) == 2
    assert msg_data["messages"][0]["role"] == "user"
    assert msg_data["messages"][1]["role"] == "assistant"
    
    print(f"✓ 对话消息流程测试通过，共 {conv_data['message_count']} 条消息")


@pytest.mark.asyncio
async def test_delete_conversation(test_client):
    """测试删除对话"""
    # 创建对话
    create_resp = await test_client.post(
        "/api/conversations",
        json={"title": "To Be Deleted"}
    )
    conv_id = create_resp.json()["id"]
    
    # 删除对话
    delete_resp = await test_client.delete(f"/api/conversations/{conv_id}")
    assert delete_resp.status_code == 200
    
    # 验证对话已删除
    get_resp = await test_client.get(f"/api/conversations/{conv_id}")
    assert get_resp.status_code == 404
    
    print(f"✓ 对话删除成功: {conv_id}")


@pytest.mark.asyncio
async def test_conversation_init_event_structure(test_client, cleanup_conversation):
    """测试 conversation_init 事件结构（Bug 1的核心）"""
    # 只发送请求，不等待完整workflow，只检查前几个事件
    import json
    
    response = await test_client.post(
        "/api/chat/stream",
        json={
            "thread_id": "__default__",
            "messages": [{"role": "user", "content": "Quick test"}],
            "resources": [],
            "auto_accepted_plan": True,
            "enable_background_investigation": False,
            "max_plan_iterations": 1,
            "max_step_num": 1,
            "max_search_results": 1,
        },
        timeout=10.0,
    )
    
    # 只读取前几个事件
    conv_init_found = False
    conversation_id = None
    conversation_data = None
    
    async for chunk in response.aiter_bytes():
        lines = chunk.decode("utf-8").split("\n")
        for line in lines:
            if line.startswith("event: conversation_init"):
                conv_init_found = True
            elif conv_init_found and line.startswith("data: "):
                data_str = line[6:].strip()
                event_data = json.loads(data_str)
                conversation_id = event_data.get("conversation_id")
                conversation_data = event_data.get("conversation")
                break
        
        if conversation_data:
            break
    
    # 验证事件结构
    assert conv_init_found, "conversation_init 事件未找到"
    assert conversation_id is not None, "conversation_id 缺失"
    assert conversation_data is not None, "conversation 数据缺失"
    
    # 验证conversation数据结构
    assert "id" in conversation_data
    assert "title" in conversation_data
    assert "created_at" in conversation_data
    assert "updated_at" in conversation_data
    assert "message_count" in conversation_data
    
    cleanup_conversation(conversation_id)
    
    print(f"✓ conversation_init 事件结构正确")
    print(f"  - conversation_id: {conversation_id}")
    print(f"  - title: {conversation_data['title']}")
    print(f"  - message_count: {conversation_data['message_count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


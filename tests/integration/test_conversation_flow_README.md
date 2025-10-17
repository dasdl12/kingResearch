# 对话功能集成测试

## 概述

这个测试套件验证了对话历史功能的两个关键bug修复：

### Bug 1: 前端sidebar未显示新对话
**问题描述**: 当用户在没有对话的情况下进入首页并开始对话时，后端会创建新对话并存入数据库，但前端sidebar没有立即显示这个新对话。

**修复方案**:
1. 后端在 `conversation_init` 事件中包含完整的对话信息（id, title, created_at, updated_at, message_count, metadata）
2. 前端在收到 `conversation_init` 事件后，立即将新对话添加到sidebar的对话列表中
3. 移除了之前依赖延迟轮询的逻辑

**测试**: `test_new_conversation_appears_in_sidebar`

### Bug 2: 对话标题未根据用户topic更新
**问题描述**: 新建对话后，对话标题没有根据用户发送的第一条消息自动更新，仍然显示为"New Conversation"。

**修复方案**:
1. 在用户发送第一条消息后，后端使用 basic LLM（**不是coordinator**）生成简洁的标题（最多6个词）
2. 标题生成立即执行（使用 await），并通过新的 `conversation_title_updated` 事件通知前端
3. 前端收到标题更新事件后，立即更新sidebar中的对话标题

**测试**: `test_conversation_title_updates_after_user_message`

## 标题生成逻辑

**问题**: 标题是如何生成的？使用coordinator吗？

**答案**: 
- **不是**使用coordinator生成的
- 使用的是 **basic LLM**（通过 `get_llm_by_type("basic")`）
- 生成提示要求生成简短的标题（最多6个词）
- 如果生成失败，会fallback到消息的前50个字符

**相关代码**: `src/server/app.py` 中的 `_auto_generate_title()` 函数

**测试**: `test_title_generation_logic`

## 运行测试

### 前置条件
1. 确保PostgreSQL数据库正在运行
2. 设置环境变量 `LANGGRAPH_CHECKPOINT_DB_URL`

### 运行命令

```bash
# 运行所有对话流程测试
pytest tests/integration/test_conversation_flow.py -v

# 运行特定测试
pytest tests/integration/test_conversation_flow.py::test_new_conversation_appears_in_sidebar -v
pytest tests/integration/test_conversation_flow.py::test_conversation_title_updates_after_user_message -v

# 运行端到端测试
pytest tests/integration/test_conversation_flow.py::test_conversation_workflow_end_to_end -v
```

## 测试覆盖

### test_new_conversation_appears_in_sidebar
验证新对话立即出现在前端sidebar中：
- ✓ `conversation_init` 事件包含完整对话数据
- ✓ 新对话可以通过API获取
- ✓ 新对话出现在对话列表中

### test_conversation_title_updates_after_user_message
验证对话标题在用户发送消息后更新：
- ✓ `conversation_title_updated` 事件被发出
- ✓ 标题不再是"New Conversation"
- ✓ 数据库中的标题已更新

### test_title_generation_logic
验证标题生成的具体逻辑：
- ✓ 使用basic LLM（不是coordinator）
- ✓ 生成简洁的标题（≤10词）
- ✓ 支持多语言（中英文）

### test_conversation_workflow_end_to_end
端到端验证完整工作流：
- ✓ 用户发送第一条消息
- ✓ 前端收到conversation_init事件
- ✓ 前端收到conversation_title_updated事件
- ✓ Sidebar显示带有正确标题的新对话
- ✓ 消息正确保存到数据库

## 预期行为

### 正常流程
1. 用户打开应用（无活动对话）
2. 用户在输入框输入问题并发送
3. 后端创建新对话，标题为"New Conversation"
4. 前端立即收到 `conversation_init` 事件，sidebar显示新对话
5. 后端生成标题（约1-3秒）
6. 前端收到 `conversation_title_updated` 事件，sidebar标题更新
7. 用户看到sidebar中有新对话，标题已更新

### 事件序列
```
1. conversation_init (立即)
   - 包含新对话的完整信息
   - 标题: "New Conversation"

2. conversation_title_updated (1-3秒后)
   - 包含生成的新标题
   - 标题: 如 "Machine Learning Basics"
```

## 清理

测试使用 `cleanup_conversation` fixture自动清理创建的测试数据。
所有测试对话在测试完成后会自动从数据库中删除。


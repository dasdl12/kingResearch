# Bug修复日志 - AIMessage-ToolMessage配对问题

## 修复日期
2025-10-16 (初次修复 + 第二次修复)

## 问题描述

### 症状
系统在运行deep research时崩溃，错误信息：
```
ValueError: Found AIMessages with tool_calls that do not have a corresponding ToolMessage.
```

### 根本原因
`src/utils/context_manager.py` 的消息压缩算法存在两个严重缺陷：

1. **缺陷1**：在从后往前压缩消息时，没有考虑 AIMessage 与 ToolMessage 之间的配对关系
   - 导致 AIMessage（包含tool_calls）被保留，但对应的 ToolMessage 被删除

2. **缺陷2**：当 AIMessage 在 prefix 中，而其 ToolMessage 在 suffix 中时，算法无法正确处理跨边界的配对关系
   - 导致 prefix 中的 AIMessage 被保留，但其 ToolMessage 被忽略或部分删除

### 触发场景
- Researcher节点同时发起多个 web_search 工具调用
- 消息历史超过 token 限制需要压缩时
- preserve_prefix_message_count 设置导致 AIMessage 在 prefix 中

## 修复方案

### 修改文件
1. `src/utils/context_manager.py` - 核心压缩逻辑
2. `tests/unit/utils/test_context_manager.py` - 添加3个新测试

### 修复内容

#### 1. Suffix部分的AIMessage-ToolMessage配对（首次修复）
- 在从后往前添加消息时，识别包含 tool_calls 的 AIMessage
- 自动收集 AIMessage 及其所有对应的 ToolMessage 作为**不可分割的组**
- 要么整组保留，要么整组删除

#### 2. Prefix-Suffix跨边界配对（第二次修复）
- 检查 prefix 最后一条消息是否为包含 tool_calls 的 AIMessage
- 如果是，从 suffix 中查找并收集所有对应的 ToolMessage
- 计算所需 token，如果空间不足，则从 prefix 中移除该 AIMessage
- 如果空间足够，将这些 ToolMessage 作为 required_tool_messages 插入到最终结果中

### 关键代码逻辑

```python
# 检查prefix最后一条消息
if prefix_messages and isinstance(prefix_messages[-1], AIMessage):
    last_ai_msg = prefix_messages[-1]
    if hasattr(last_ai_msg, 'tool_calls') and last_ai_msg.tool_calls:
        # 收集对应的ToolMessages
        required_tool_messages = [...]
        
        # 检查是否有足够空间
        if required_tokens > available_token:
            # 移除AIMessage
            prefix_messages.pop()
        else:
            # 保留AIMessage和所有ToolMessages
            available_token -= required_tokens

# 最终返回
return prefix_messages + required_tool_messages + suffix_messages
```

## 测试验证

### 新增测试用例
1. `test_compress_messages_preserves_aimessage_toolmessage_pairs`
   - 验证 suffix 中的 AIMessage-ToolMessage 配对保留

2. `test_compress_messages_excludes_incomplete_tool_pairs`
   - 验证空间不足时整组被排除

3. `test_compress_messages_preserves_aimessage_toolmessage_across_prefix_suffix`
   - 验证跨 prefix-suffix 边界的配对处理

### 测试结果
✅ 所有21个单元测试通过（原18个 + 新增3个）

## 影响范围

### 修复前
- 任何使用多个工具调用的 agent 场景都会失败
- Researcher节点无法正常完成研究任务
- 违反 LangChain 的消息历史完整性要求

### 修复后
- AIMessage-ToolMessage 配对完整性得到保证
- 支持跨边界配对场景
- 符合 LangChain 的验证要求
- Deep research 可以正常运行

## 后续建议

1. 监控生产环境中的消息压缩日志
2. 如果频繁出现 AIMessage 被从 prefix 中移除的情况，考虑：
   - 增加 token_limit
   - 减少 preserve_prefix_message_count
   - 优化工具调用结果的大小

3. 考虑添加更智能的压缩策略：
   - 选择性截断 ToolMessage 内容而非完全删除
   - 优先保留最近的工具调用结果


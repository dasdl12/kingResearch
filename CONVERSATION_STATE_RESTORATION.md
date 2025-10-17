# 对话状态恢复方案

## 当前问题

### 消息保存现状
1. ✅ **用户消息**：保存到`messages`表
2. ❌ **AI消息（plan/research/report）**：只保存在langgraph checkpoint，不在messages表
3. ❌ **切换对话后**：前端只从messages表加载，看不到AI回复

### 具体场景

**场景1：只生成plan还没开始research**
- 问题：Plan内容只在checkpoint中，切换后看不到
- 影响：用户以为对话丢失了

**场景2：研究到一半切换对话**
- 问题：Research进度只在checkpoint中，切换后看不到
- 影响：用户无法查看中间结果

## 解决方案选项

### 方案A：保存AI消息到messages表（推荐）

**优点**：
- 简单的消息查询和导出
- 不依赖checkpoint即可查看历史
- 支持全文搜索

**缺点**：
- 需要在workflow中每个消息完成时保存
- 可能有重复保存的问题

### 方案B：从checkpoint恢复state

**优点**：
- 完整恢复workflow状态（包括plan、research进度）
- 可以继续未完成的研究
- 数据一致性好

**缺点**：
- 复杂度高
- 需要处理checkpoint格式
- 查询性能可能较差

### 方案C：混合方案（最佳）

**实现**：
1. 关键节点完成时保存AI消息到messages表：
   - Coordinator完成：保存初始对话
   - Planner完成：保存plan（JSON格式）
   - Reporter完成：保存最终报告
2. 切换对话时：
   - 先从messages表加载基本消息
   - 如果有checkpoint，显示"继续研究"按钮
   - 点击后从checkpoint恢复完整state

## 实现计划

### 步骤1：保存关键AI消息

在planner和reporter节点完成后保存消息：

```python
# src/graph/nodes.py

def planner_node(state: State, config: RunnableConfig):
    # ... existing code ...
    
    # Save plan to messages table
    conversation_id = state.get("conversation_id")
    if conversation_id and isinstance(curr_plan, dict):
        from src.database.models import MessageRepository, Message as DBMessage
        msg_repo = MessageRepository()
        try:
            db_message = DBMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=json.dumps(curr_plan, ensure_ascii=False),
                agent="planner",
                metadata={"type": "plan", "plan_data": curr_plan}
            )
            msg_repo.add_message(db_message)
        finally:
            msg_repo.close()
```

### 步骤2：前端加载时解析不同类型的消息

```typescript
// 加载消息时识别消息类型
for (const msg of messagesData.messages) {
  if (msg.agent === "planner" && msg.metadata?.type === "plan") {
    // 解析plan并显示
    const planData = JSON.parse(msg.content);
    // 添加plan到UI
  } else {
    // 普通消息
    messagesMap.set(msg.id, {
      id: msg.id,
      content: msg.content,
      // ...
    });
  }
}
```

### 步骤3：添加"继续研究"功能

如果checkpoint中有未完成的workflow，显示按钮允许继续。

## 临时解决方案（快速）

在我重新应用所有app.py修改之前，你可以：

1. **避免在研究中切换对话**：等research完成后再切换
2. **使用导出功能**：导出对话保存中间结果
3. **不要删除browser的对话**：这样至少checkpoint还在

## 接下来我要做的

我误操作覆盖了app.py，需要重新应用所有修改。让我创建一个脚本来恢复。


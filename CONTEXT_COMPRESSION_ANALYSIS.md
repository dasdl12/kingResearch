# 上下文压缩机制分析与优化建议

## 📊 问题现状

从实际运行日志分析：
```
Message compression completed: 2998889 -> 151583 tokens (reduction: 94.9%)
```

单次Deep Research上下文达到**300万tokens**，压缩后约15万tokens。

## 🔍 Token消耗分析

### Token来源占比估算

| 来源 | 每次占比 | 累计30次搜索 | 说明 |
|------|---------|------------|------|
| **raw_content** | 30,000 tokens/次 | ~900,000 tokens | **主要元凶** - 完整网页原始内容 |
| content摘要 | 3,000 tokens/次 | ~90,000 tokens | Tavily提供的精炼摘要 |
| AI分析内容 | 10,000 tokens/步 | ~100,000 tokens | 每个research步骤的findings |
| 历史消息 | - | ~50,000 tokens | 对话历史累积 |
| 图片描述 | 500 tokens/次 | ~15,000 tokens | 图片AI描述 |
| 元数据 | - | ~10,000 tokens | 工具调用、状态等 |

**总计：约 1,165,000 tokens（仅估算，实际可能因内容长度波动）**

### raw_content的问题

1. **包含大量无用信息**：
   - 网页导航栏、页脚、广告
   - HTML标记残留
   - 重复内容

2. **与content高度重复**：
   - Tavily已经提供了精炼的`content`字段
   - `raw_content`通常只是冗余信息

3. **token消耗惊人**：
   - 单个网页raw_content: 5,000-20,000 tokens
   - 相比content摘要: 500-1,000 tokens
   - **膨胀比例：10-20倍**

## 🛠️ 当前上下文压缩机制

### 工作原理（src/utils/context_manager.py）

#### 1. **分层保护策略**

```python
def _intelligent_compress(self, messages):
    # 策略1: 保护前N条消息（系统提示词等）
    prefix_count = self.preserve_prefix_message_count  # 默认3
    
    # 策略2: 滑动窗口保护最近消息
    recent_messages = messages[-self.sliding_window_size:]  # 默认5
    
    # 策略3: 压缩中间旧消息
    older_messages = messages[prefix_count:-sliding_window_size]
```

#### 2. **压缩方法**

对于旧消息（特别是ToolMessage）：

**A. JSON智能压缩**（新增修复）
```python
def _try_compress_json(self, content, max_tokens):
    # 识别JSON格式的工具结果
    data = json.loads(content)
    
    if isinstance(data, list):
        # 保留首尾元素，删除中间
        return [data[0], data[-1]]
    
    elif isinstance(data, dict):
        # 保留关键字段：url, title, score等
        return {k: v for k, v in data.items() if k in priority_fields}
```

**B. 基于规则的摘要**
```python
def _summarize_message(self, message, max_tokens=300):
    # 提取<finding>标签内容
    findings = re.findall(r'<finding>(.*?)</finding>', content)
    
    # 保留首尾，压缩中间
    summary = [findings[0], f"[... {len(findings)-2} findings omitted ...]", findings[-1]]
```

**C. 直接截断**
```python
def _truncate_message_content(self, message, max_tokens):
    char_limit = max_tokens * 2
    return content[:char_limit] + "... [truncated]"
```

#### 3. **Token预算分配**

```python
# 60%预算给旧消息，40%给最近消息
older_budget = available_tokens * 0.6
recent_budget = available_tokens * 0.4
```

#### 4. **压缩效果**

从实际运行看：
- 压缩前：2,998,889 tokens
- 压缩后：151,583 tokens
- **压缩率：94.9%** ✅

这已经是非常高效的压缩！但根源问题是输入了太多无用数据。

## ✅ 优化建议

### 建议1：禁用raw_content（强烈推荐）

**配置方法**：
在`conf.yaml`中添加：

```yaml
SEARCH_ENGINE:
  engine: tavily
  include_raw_content: false  # 禁用raw_content
  include_images: true
  max_content_length_per_page: 5000  # 限制content长度
  min_score_threshold: 0.4  # 过滤低质量结果
```

**预期效果**：
- Token消耗减少 **60-70%**
- 从300万降至约90-120万tokens
- 搜索质量**几乎不受影响**（content已经足够）

**是否有必要包含raw_content？**

❌ **大多数情况下不需要**：
- Tavily的`content`字段已经是AI优化的摘要
- 对于deep research，摘要信息已足够
- raw_content只会带来噪音和token浪费

✅ **仅在以下情况需要**：
- 需要提取特定细节（如表格数据、代码片段）
- 需要验证引用的准确性
- content摘要质量不佳

### 建议2：优化搜索后处理

```yaml
SEARCH_ENGINE:
  engine: tavily
  include_raw_content: false
  max_content_length_per_page: 3000  # 每页限制3000字符
  min_score_threshold: 0.5  # 提高质量阈值
```

### 建议3：减少搜索次数

调整配置：
```yaml
max_search_results: 2  # 从3减少到2
max_step_num: 5  # 限制研究步骤数
```

### 建议4：使用更大token limit的模型

```yaml
BASIC_MODEL:
  model: "openai/gpt-5-nano"
  token_limit: 250000  # 当前
  
# 改为：
BASIC_MODEL:
  model: "google/gemini-2.5-pro"  # 支持更大上下文
  token_limit: 2000000  # 减少压缩频率
```

## 📈 优化效果预测

| 优化措施 | Token减少 | 质量影响 | 推荐度 |
|---------|----------|---------|-------|
| 禁用raw_content | -60% | ⭐⭐⭐⭐⭐ 几乎无影响 | ⭐⭐⭐⭐⭐ |
| 限制content长度 | -10% | ⭐⭐⭐⭐ 轻微影响 | ⭐⭐⭐⭐ |
| 提高score阈值 | -5% | ⭐⭐⭐⭐⭐ 反而提升质量 | ⭐⭐⭐⭐⭐ |
| 减少搜索结果数 | -15% | ⭐⭐⭐ 中等影响 | ⭐⭐⭐ |

**组合优化预期**：
- Token消耗：300万 → **60-80万** tokens（减少73-80%）
- 压缩后：15万 → **5-8万** tokens
- 研究质量：**几乎不受影响**，甚至因过滤噪音而提升

## 🎯 推荐配置

```yaml
SEARCH_ENGINE:
  engine: tavily
  include_raw_content: false  # ⭐ 核心优化
  include_images: true
  include_image_descriptions: true
  max_content_length_per_page: 3000  # 限制单页长度
  min_score_threshold: 0.5  # 过滤低质量结果
```

## 🔧 现有压缩机制评价

### 优点 ✅
1. **多层保护**：保护系统消息、最近消息
2. **智能识别JSON**：新增的JSON压缩避免破坏结构
3. **压缩率高**：94.9%的压缩率已经很优秀
4. **自适应**：根据token budget动态调整

### 可改进之处 💡
1. **更激进的ToolMessage压缩**：
   - 当前对ToolMessage压缩到300 tokens
   - 可以进一步压缩到100-150 tokens
   
2. **智能去重**：
   - 检测重复的搜索结果
   - 合并相似内容

3. **优先级排序**：
   - 保留高score的搜索结果
   - 删除低score的完整内容

4. **语义压缩**：
   - 使用小模型对长文本做语义摘要
   - 而不是简单截断

## 📝 总结

**问题根源**：`include_raw_content: true` 引入了大量冗余数据

**最佳解决方案**：
1. 立即禁用`raw_content`（减少60-70% token）
2. 设置合理的`max_content_length_per_page`
3. 现有压缩机制已经很优秀，无需大改

**现有压缩机制运作良好**：
- 分层保护策略合理
- JSON智能压缩（已修复bug）
- 94.9%压缩率优秀

**关键认知**：
> 上下文压缩是治标不治本，应该从源头减少无用数据的引入。禁用raw_content是最有效的优化手段。


# 用户认证与对话历史功能实现文档

## 🎯 功能概述

实现多用户认证和对话历史管理功能，用户可以：
- 注册/登录账号
- 查看自己的历史研究
- 点击历史记录直接查看完整的研究报告和流程（非回放模式）
- 删除自己的研究记录
- 数据完全隔离（用户只能看到自己的数据）

## ✅ 已完成的工作

### 1. 后端认证模块 ✅
- [x] JWT token 生成和验证 (`src/auth/jwt_handler.py`)
- [x] 密码加密（bcrypt）(`src/auth/password.py`)
- [x] FastAPI 认证依赖注入 (`src/auth/dependencies.py`)
- [x] 认证请求/响应模型 (`src/server/auth_request.py`)

### 2. 数据库设计 ✅
- [x] 创建用户表 (users)
- [x] 修改 research_replays 表，添加：
  - `user_id` - 用户ID（外键）
  - `is_completed` - 是否完成
  - `final_report` - 完整报告
  - `observations` - 研究过程（JSONB）
  - `plan` - 研究计划（JSONB）
  - `completed_at` - 完成时间
- [x] 数据库迁移脚本 (`migrations/001_create_users_and_add_user_id.sql`)

### 3. Checkpoint管理 ✅
- [x] 修改 `ChatStreamManager` 类
- [x] 实现 `save_completed_research()` - **只保存完成的研究**
- [x] 实现 `get_user_researches()` - 获取用户研究列表
- [x] 实现 `get_research_report()` - 获取完整研究数据（包括observations和plan）
- [x] 实现 `delete_research()` - 删除研究（带所有权验证）
- [x] 所有操作都验证user_id，确保数据隔离

### 4. 研究流程集成 ✅  
- [x] 修改 `Configuration` 类，添加 `thread_id` 和 `user_id` 字段
- [x] 修改 `reporter_node`，在生成报告后自动保存完整研究数据

## 🚧 待完成的工作

### 5. API 端点（进行中）⏳
需要在 `src/server/app.py` 添加：

```python
# 认证相关
POST /api/auth/register  # 用户注册
POST /api/auth/login     # 用户登录  
GET  /api/auth/me        # 获取当前用户信息

# 研究历史相关
GET  /api/researches                  # 获取用户的研究列表
GET  /api/research/{thread_id}        # 获取完整研究数据（observations + plan + report）
DELETE /api/research/{thread_id}      # 删除研究

# 修改现有接口
POST /api/chat/stream                 # 添加user_id到config
```

### 6. 前端实现 📱
- [ ] 创建 AuthContext (`web/src/core/auth/context.tsx`)
- [ ] 登录/注册页面 (`web/src/app/auth/page.tsx`)
- [ ] 修改对话列表组件 (`web/src/app/settings/dialogs/conversations-dialog.tsx`)
  - 显示用户自己的研究列表
  - 点击时加载完整数据并直接展示
- [ ] 修改chat页面，支持从历史记录加载完整state
- [ ] 添加token到所有API请求

### 7. 数据展示逻辑 🎨
**关键点：与回放模式的区别**

#### 回放模式（现有）:
```
1. 加载replay文本文件
2. 逐行解析SSE事件
3. 慢慢播放，模拟实时效果
```

#### 历史查看模式（新功能）:
```
1. 调用 GET /api/research/{thread_id}
2. 返回完整数据：
   {
     final_report: "...",
     observations: ["step1 result", "step2 result", ...],
     plan: { title: "...", steps: [...] },
     research_topic: "...",
     ...
   }
3. 前端直接渲染：
   - Activity面板：显示所有observations
   - Report面板：显示final_report
   - 不需要SSE流式传输
   - 立即显示所有内容
```

## 📦 依赖包

需要添加到 `requirements.txt`:
```
passlib[bcrypt]>=1.7.4
PyJWT>=2.8.0
python-multipart>=0.0.6
```

## 🔧 环境变量配置

在 `.env` 或环境变量中添加：
```bash
# JWT密钥（生产环境必须使用强随机字符串）
JWT_SECRET_KEY=your-super-secret-key-change-this-in-production

# PostgreSQL连接（如果使用PostgreSQL）
LANGGRAPH_CHECKPOINT_DB_URL=postgresql://user:password@localhost:5432/deerflow

# 启用checkpoint功能
LANGGRAPH_CHECKPOINT_SAVER=true
```

## 🗄️ 数据库迁移步骤

```bash
# 1. 连接到PostgreSQL数据库
psql -d deerflow -U your_username

# 2. 运行迁移脚本
\i migrations/001_create_users_and_add_user_id.sql

# 3. 验证表结构
\d users
\d research_replays
```

## 🔐 认证流程

### 注册流程:
```
1. 用户提交：username, email, password
2. 后端：
   - 验证用户名/邮箱唯一性
   - 使用bcrypt加密密码
   - 插入users表
   - 生成JWT token
3. 返回：token + user_id
4. 前端：保存token到localStorage
```

### 登录流程:
```
1. 用户提交：username (或email), password
2. 后端：
   - 查询用户
   - 验证密码
   - 生成JWT token
3. 返回：token + user_id
4. 前端：保存token到localStorage
```

### API调用流程:
```
1. 前端：从localStorage读取token
2. 请求头：Authorization: Bearer <token>
3. 后端：验证token，提取user_id
4. 执行操作（自动过滤用户数据）
```

## 🎬 完整使用流程

### 用户视角：

1. **首次使用**:
   ```
   访问网站 → 注册账号 → 登录成功 → 进入研究界面
   ```

2. **进行研究**:
   ```
   输入研究问题 → 等待完成 → 自动保存到数据库
   （保存内容：final_report + observations + plan + user_id）
   ```

3. **查看历史**:
   ```
   点击"对话历史"图标 → 看到自己的研究列表 → 点击某个研究
   → 立即展示完整报告和研究流程（activity + report）
   ```

4. **删除研究**:
   ```
   在历史列表中点击删除 → 确认 → 从数据库删除
   ```

## 🔒 安全考虑

1. **密码安全**: 使用bcrypt加密，不存储明文
2. **Token安全**: JWT有效期7天，使用HTTPS传输
3. **数据隔离**: 所有查询都添加user_id过滤
4. **SQL注入**: 使用参数化查询
5. **XSS防护**: 前端使用React自动转义

## 📊 数据存储结构

### research_replays表结构:
```sql
CREATE TABLE research_replays (
    id UUID PRIMARY KEY,
    thread_id VARCHAR(255),
    user_id UUID REFERENCES users(id),  -- 关联用户
    research_topic VARCHAR(500),
    report_style VARCHAR(50),
    final_report TEXT,                  -- 最终报告
    observations JSONB,                 -- 研究过程 ["step1 result", "step2 result"]
    plan JSONB,                         -- 研究计划 {title: "", steps: []}
    is_completed BOOLEAN,               -- 只有TRUE的才显示
    created_at TIMESTAMP,
    completed_at TIMESTAMP,
    ts TIMESTAMP
);
```

## 🐛 测试检查清单

- [ ] 用户注册功能正常
- [ ] 用户登录功能正常
- [ ] Token验证正常
- [ ] 完成研究后自动保存
- [ ] 只能看到自己的研究列表
- [ ] 点击历史记录能正确展示完整数据
- [ ] 删除研究功能正常（带所有权验证）
- [ ] 多用户数据完全隔离
- [ ] 未登录用户无法访问受保护接口

## 📝 核心代码位置

```
src/
├── auth/                          # 认证模块
│   ├── __init__.py
│   ├── jwt_handler.py             # JWT处理
│   ├── password.py                # 密码加密
│   └── dependencies.py            # 认证依赖
├── graph/
│   ├── checkpoint.py              # ✅ 研究保存/读取（已完成）
│   └── nodes.py                   # ✅ reporter_node保存逻辑（已完成）
├── config/
│   └── configuration.py           # ✅ 添加thread_id和user_id（已完成）
├── server/
│   ├── app.py                     # ⏳ API端点（待添加）
│   └── auth_request.py            # ✅ 认证模型（已完成）
└── migrations/
    └── 001_create_users_and_add_user_id.sql  # ✅ 数据库迁移（已完成）

web/src/
├── core/
│   └── auth/
│       └── context.tsx            # ⏳ 认证上下文（待实现）
└── app/
    ├── auth/
    │   └── page.tsx               # ⏳ 登录页面（待实现）
    └── settings/dialogs/
        └── conversations-dialog.tsx  # ⏳ 对话历史（待修改）
```

## 🚀 下一步行动

1. **立即执行数据库迁移**
2. **完成API端点实现**
3. **实现前端认证和历史查看**
4. **测试完整流程**

---

**重要提示**: 
- ✅ **已实现保存完整研究数据**（包括observations和plan）
- ✅ **只保存已完成的研究**（有final_report的才保存）
- ⚠️ **点击历史记录直接展示，不是回放模式**









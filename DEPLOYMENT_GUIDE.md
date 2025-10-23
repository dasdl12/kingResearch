# 🚀 DeerFlow 多用户部署指南

## ✅ 已实现的功能

### 核心功能
- ✅ **用户认证系统** - JWT token + bcrypt密码加密
- ✅ **数据完全隔离** - 每个用户只能看到自己的研究
- ✅ **研究历史管理** - 保存完整的研究过程（report + observations + plan）
- ✅ **直接查看模式** - 点击历史记录立即展示完整内容（非回放）
- ✅ **删除研究功能** - 带所有权验证
- ✅ **向后兼容** - 未登录用户仍可使用基本研究功能

### 技术亮点
- 🔒 **只保存完成的研究** - 未完成的研究不占用存储空间
- 🎯 **完整流程数据** - 保存 observations 和 plan，可完整回顾研究过程
- 🚀 **自动初始化** - 首次启动自动创建所有数据库表
- 🔐 **简单配额** - 每用户每日研究次数限制

---

## 📦 第一步：安装依赖

### Python依赖
```bash
cd deer-flow

# 使用uv（推荐，更快）
uv pip install -e .

# 或使用pip
pip install -e .
```

新增的依赖（已添加到pyproject.toml）：
- `passlib[bcrypt]>=1.7.4` - 密码加密
- `PyJWT>=2.8.0` - JWT token
- `python-multipart>=0.0.6` - 文件上传支持

### 前端依赖
```bash
cd web
npm install
# 或
pnpm install
```

---

## 🗄️ 第二步：配置PostgreSQL

### 创建数据库
```bash
# Windows (使用psql)
createdb deerflow

# 或者在pgAdmin中创建名为 'deerflow' 的数据库
```

### 配置环境变量

在 `deer-flow/.env` 文件中添加（如果没有就创建）：

```bash
# ========== 数据库配置 ==========
LANGGRAPH_CHECKPOINT_SAVER=true
LANGGRAPH_CHECKPOINT_DB_URL=postgresql://postgres:your_password@localhost:5432/deerflow

# ========== JWT密钥（重要！生产环境必须修改） ==========
JWT_SECRET_KEY=your-super-secret-random-string-please-change-this-in-production

# ========== CORS配置 ==========
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001

# ========== 其他配置 ==========
# 你的其他配置保持不变...
```

**重要提示**：
- 🔐 `JWT_SECRET_KEY` 生产环境必须使用强随机字符串（至少32字符）
- 📝 替换 `your_password` 为你的PostgreSQL密码
- 🌐 生产环境需要在 `ALLOWED_ORIGINS` 添加你的域名

生成强随机密钥的方法：
```python
import secrets
print(secrets.token_urlsafe(32))
# 输出类似：k8Gx3vN9mP2qR5tY7wZ1aB4cD6fH8jL0nM3pQ5sT9vX2
```

---

## 🎬 第三步：启动应用

### 启动后端
```bash
cd deer-flow

# 开发模式（自动重载）
python -m uvicorn src.server.app:app --reload --host 0.0.0.0 --port 8000

# 或使用生产模式
uvicorn src.server.app:app --host 0.0.0.0 --port 8000
```

**首次启动时会自动创建所有表**，查看日志应该看到：
```
INFO: Users table created/verified successfully
INFO: Chat streams table created/verified successfully  
INFO: Research replays table created/verified successfully
```

### 启动前端
```bash
cd web

# 开发模式
npm run dev
# 或
pnpm dev

# 访问 http://localhost:3000
```

---

## 🧪 第四步：测试功能

### 1. 测试用户注册
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "test123456",
    "display_name": "Test User"
  }'
```

**成功响应**：
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user_id": "uuid-here",
  "username": "testuser",
  "display_name": "Test User"
}
```

### 2. 测试用户登录
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "test123456"
  }'
```

### 3. 测试获取用户信息
```bash
# 使用上面获取的token
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 4. 测试研究流程

#### 4.1 进行一次研究（通过前端）
1. 访问 http://localhost:3000
2. 点击右上角"Sign In"登录
3. 输入研究问题，完成研究
4. 研究完成后会自动保存到数据库

#### 4.2 查看研究历史
1. 点击顶部工具栏的 📝 图标（Research History）
2. 看到你的研究列表
3. 点击"View"按钮查看完整研究

#### 4.3 验证数据隔离
```bash
# 直接查询数据库验证
psql -d deerflow -c "SELECT thread_id, user_id, research_topic, is_completed FROM research_replays;"
```

---

## 📱 前端使用指南

### 新增页面和功能

#### 1. 登录/注册页面
- 路径：`/auth`
- 功能：用户注册和登录
- 特点：支持"不登录继续使用"选项

#### 2. 研究查看页面
- 路径：`/research/[threadId]`  
- 功能：查看完整的研究报告和流程
- 布局：
  - 左侧：研究计划 + 过程（Observations）
  - 右侧：最终报告（Final Report）

#### 3. Header新增元素
- 👤 用户图标（已登录时显示）
- 📝 研究历史按钮
- 🔐 登录/注销按钮

---

## 🔑 API文档

### 认证API

#### POST /api/auth/register
注册新用户

**Request:**
```json
{
  "username": "myusername",
  "email": "user@example.com",
  "password": "password123",
  "display_name": "My Name"  // 可选
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user_id": "uuid",
  "username": "myusername",
  "display_name": "My Name"
}
```

#### POST /api/auth/login
用户登录

**Request:**
```json
{
  "username": "myusername",  // 或者使用email
  "password": "password123"
}
```

**Response:** 同上

#### GET /api/auth/me
获取当前用户信息（需要认证）

**Headers:**
```
Authorization: Bearer YOUR_TOKEN
```

**Response:**
```json
{
  "user_id": "uuid",
  "username": "myusername",
  "email": "user@example.com",
  "display_name": "My Name",
  "created_at": "2025-10-22T10:00:00",
  "daily_quota": 10,
  "used_today": 3
}
```

### 研究历史API

#### GET /api/researches?limit=20&offset=0
获取用户的研究列表（需要认证）

**Headers:**
```
Authorization: Bearer YOUR_TOKEN
```

**Response:**
```json
{
  "data": [
    {
      "id": "uuid",
      "thread_id": "thread-uuid",
      "research_topic": "How does AI work?",
      "report_style": "academic",
      "is_completed": true,
      "created_at": "2025-10-22T10:00:00",
      "completed_at": "2025-10-22T10:15:00",
      "ts": "2025-10-22T10:15:00"
    }
  ]
}
```

#### GET /api/research/{thread_id}
获取完整研究数据（需要认证）

**Headers:**
```
Authorization: Bearer YOUR_TOKEN
```

**Response:**
```json
{
  "id": "uuid",
  "thread_id": "thread-uuid",
  "research_topic": "How does AI work?",
  "report_style": "academic",
  "final_report": "# AI Overview\n\n...",
  "observations": [
    "Step 1 result: Found 10 articles...",
    "Step 2 result: Analyzed data..."
  ],
  "plan": {
    "title": "Research Plan",
    "thought": "We need to...",
    "steps": [
      {
        "title": "Search for AI basics",
        "description": "Find fundamental concepts",
        "step_type": "research"
      }
    ],
    "has_enough_context": true
  },
  "is_completed": true,
  "completed_at": "2025-10-22T10:15:00"
}
```

#### DELETE /api/research/{thread_id}
删除研究（需要认证，验证所有权）

**Headers:**
```
Authorization: Bearer YOUR_TOKEN
```

**Response:**
```json
{
  "message": "Research deleted successfully"
}
```

---

## 🔐 安全特性

### 已实现
- ✅ JWT token认证（7天有效期）
- ✅ bcrypt密码加密（强度12）
- ✅ 所有权验证（用户只能访问自己的数据）
- ✅ SQL注入防护（参数化查询）
- ✅ 密码最小长度要求（6字符）
- ✅ 账号状态控制（is_active字段）

### 生产环境建议
- 🌐 **必须使用HTTPS**（保护token传输）
- 🔑 **修改JWT_SECRET_KEY**为强随机字符串
- 🛡️ 添加Rate Limiting（防止暴力破解）
- 📧 添加邮箱验证
- 🔄 实现Token刷新机制
- 🔒 添加CORS白名单限制

---

## 📊 数据库表结构

### users 表
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    daily_quota INTEGER DEFAULT 10,
    used_today INTEGER DEFAULT 0,
    last_reset_date DATE DEFAULT CURRENT_DATE
);
```

### research_replays 表
```sql
CREATE TABLE research_replays (
    id UUID PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    research_topic VARCHAR(500) NOT NULL,
    report_style VARCHAR(50) NOT NULL,
    final_report TEXT,                    -- 最终报告
    observations JSONB,                   -- 研究过程步骤
    plan JSONB,                           -- 研究计划
    is_completed BOOLEAN DEFAULT FALSE,   -- 只有TRUE的才显示
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

---

## 🎯 使用流程示例

### 场景1：新用户使用

```
1. 用户访问 http://localhost:3000
2. 点击右上角"登录"图标
3. 点击"还没有账号？去注册"
4. 填写注册信息：
   - 用户名：alice
   - 邮箱：alice@example.com
   - 密码：alice123
5. 自动登录，跳转到聊天界面
6. 输入研究问题："人工智能如何影响教育？"
7. 等待研究完成（会自动保存）
8. 点击📝图标查看历史
9. 看到刚才的研究，点击"View"
10. 立即看到完整的报告和研究过程
```

### 场景2：多用户数据隔离验证

```
# 用户A（alice）进行研究
1. alice登录 → 研究"AI in education" → 完成

# 用户B（bob）注册并研究
2. bob注册 → 研究"Blockchain basics" → 完成

# 验证隔离
3. alice查看历史 → 只看到"AI in education"
4. bob查看历史 → 只看到"Blockchain basics"
5. ✅ 数据完全隔离！
```

---

## 🔍 故障排查

### 问题1：无法连接数据库
```
错误: Failed to connect to PostgreSQL

解决：
1. 检查PostgreSQL是否运行：
   sc query postgresql-x64-15  # Windows
   
2. 检查连接字符串：
   LANGGRAPH_CHECKPOINT_DB_URL=postgresql://postgres:password@localhost:5432/deerflow
   
3. 测试连接：
   psql -d deerflow -U postgres
```

### 问题2：Token验证失败
```
错误: 401 Unauthorized

解决：
1. 检查前端是否保存了token：
   localStorage.getItem('auth_token')
   
2. 检查JWT_SECRET_KEY是否匹配
3. Token可能过期（7天），重新登录
```

### 问题3：研究没有保存
```
解决：
1. 检查LANGGRAPH_CHECKPOINT_SAVER=true
2. 查看后端日志是否有错误
3. 确认研究已完成（有final_report）
4. 查询数据库：
   SELECT * FROM research_replays WHERE is_completed=true;
```

### 问题4：看不到研究历史
```
解决：
1. 确认已登录（检查user图标是否显示）
2. 确认至少完成过一次研究
3. 打开浏览器Console查看是否有API错误
4. 检查数据库：
   SELECT * FROM research_replays WHERE user_id='your-uuid' AND is_completed=true;
```

---

## 🧪 测试核心功能

### 测试脚本
创建 `test_auth.sh`:

```bash
#!/bin/bash

BASE_URL="http://localhost:8000"

echo "=== 1. Register User ==="
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser1",
    "email": "test1@example.com",
    "password": "test123456"
  }')

echo $REGISTER_RESPONSE | jq .
TOKEN=$(echo $REGISTER_RESPONSE | jq -r '.access_token')

echo -e "\n=== 2. Get User Info ==="
curl -s "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer $TOKEN" | jq .

echo -e "\n=== 3. Get Researches (Should be empty) ==="
curl -s "$BASE_URL/api/researches?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .

echo -e "\n✅ Authentication working!"
```

运行：
```bash
chmod +x test_auth.sh
./test_auth.sh
```

---

## 📈 监控和维护

### 查看用户统计
```sql
-- 用户数量
SELECT COUNT(*) as total_users FROM users;

-- 活跃用户（今天使用过的）
SELECT COUNT(*) as active_today FROM users 
WHERE used_today > 0 AND last_reset_date = CURRENT_DATE;

-- 完成的研究总数
SELECT COUNT(*) as total_researches FROM research_replays 
WHERE is_completed = true;

-- 每用户研究数量
SELECT u.username, COUNT(r.id) as research_count
FROM users u
LEFT JOIN research_replays r ON u.id = r.user_id AND r.is_completed = true
GROUP BY u.id, u.username
ORDER BY research_count DESC;
```

### 清理过期数据
```sql
-- 删除30天前的研究（可选）
DELETE FROM research_replays 
WHERE completed_at < NOW() - INTERVAL '30 days';

-- 重置每日配额（定时任务）
UPDATE users 
SET used_today = 0, last_reset_date = CURRENT_DATE
WHERE last_reset_date < CURRENT_DATE;
```

---

## 🌐 生产环境部署

### 使用Docker Compose

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: deerflow
      POSTGRES_USER: deerflow_user
      POSTGRES_PASSWORD: strong_password_here
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  backend:
    build: ./deer-flow
    environment:
      LANGGRAPH_CHECKPOINT_SAVER: "true"
      LANGGRAPH_CHECKPOINT_DB_URL: "postgresql://deerflow_user:strong_password_here@postgres:5432/deerflow"
      JWT_SECRET_KEY: "your-super-secret-key-change-this"
      ALLOWED_ORIGINS: "https://yourdomain.com"
    ports:
      - "8000:8000"
    depends_on:
      - postgres

  frontend:
    build: ./deer-flow/web
    environment:
      NEXT_PUBLIC_API_URL: "https://api.yourdomain.com"
    ports:
      - "3000:3000"
    depends_on:
      - backend

volumes:
  postgres_data:
```

### 使用Nginx反向代理

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## ✨ 与旧版本对比

### 之前（单用户）:
- ❌ 无用户系统
- ❌ 所有人共享数据
- ❌ 无法区分谁做的研究
- ❌ 不安全

### 现在（多用户）:
- ✅ 完整的用户认证
- ✅ 数据完全隔离
- ✅ 每个用户管理自己的历史
- ✅ 可以安全地部署到公网

---

## 🎓 核心概念

### 什么是"只保存完成的研究"？

**完成的标准**：
- ✅ 有 `final_report`（reporter_node返回的报告）
- ✅ 研究流程走完（到达END节点）
- ❌ 中途退出的研究不保存
- ❌ 失败的研究不保存

**保存的时机**：
- 在 `reporter_node` 中
- 生成final_report之后
- 调用 `save_completed_research()`

### 什么是"直接查看"而非"回放"？

**回放模式（旧）**：
```
加载replay.txt → 解析SSE事件 → 逐条播放 → 慢慢显示
```

**直接查看模式（新）**：
```
GET /api/research/{thread_id} → 返回完整数据 → 立即渲染所有内容
```

**区别**：
- 回放：模拟实时过程，慢慢显示
- 直接查看：立即显示全部，像看文档一样

---

## 📞 技术支持

如果遇到问题：
1. 查看后端日志：uvicorn输出
2. 查看前端Console：浏览器F12
3. 查看数据库：`psql -d deerflow`
4. 检查本文档的故障排查部分

---

**最后更新时间**: 2025-10-22  
**版本**: v1.0 - 多用户认证与历史管理


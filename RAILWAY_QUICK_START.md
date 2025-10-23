# 🚂 Railway 部署快速指南

## ⚡ 3 步完成部署

### 准备工作（本地）

**1. 生成 JWT 密钥**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# 复制输出结果，例如：k8Gx3vN9mP2qR5tY7wZ1aB4cD6fH8jL0nM3pQ5sT9vX2
```

**2. 配置 conf.yaml**
```bash
cp conf.yaml.example conf.yaml
# 编辑 conf.yaml，至少填写：
```

```yaml
BASIC_MODEL:
  base_url: https://api.openai.com/v1  # 你的 LLM API 地址
  model: "gpt-4o-mini"                  # 模型名称
  api_key: "sk-your-api-key-here"      # 你的 API Key
```

**3. 提交代码**
```bash
git add .
git commit -m "准备 Railway 部署"
git push origin main
```

---

### Railway 部署

#### 步骤 1: 创建项目 + 数据库

1. 访问 https://railway.app/new
2. 选择 **"Deploy from GitHub repo"** → 选择你的仓库
3. 在项目中点击 **"+ New"** → **"Database"** → **"Add PostgreSQL"**

#### 步骤 2: 配置后端环境变量

在**后端服务**的 **Variables** 标签，添加以下变量：

```bash
# === 数据库（必需）===
LANGGRAPH_CHECKPOINT_SAVER=true
LANGGRAPH_CHECKPOINT_DB_URL=${{Postgres.DATABASE_URL}}

# === JWT 密钥（必需）===
JWT_SECRET_KEY=StxppAjus-oAB7rq_jd-aX4paGC_Tj3R5VHDycQBiAI

# === CORS（必需）===
ALLOWED_ORIGINS=https://*.railway.app

# === 搜索引擎（必需）===
SEARCH_API=tavily
TAVILY_API_KEY=<你的 Tavily API Key，从 https://app.tavily.com/ 获取>

# === 其他 ===
ENVIRONMENT=production
LOG_LEVEL=info
```

**重要提示**：
- `${{Postgres.DATABASE_URL}}` 会自动替换为数据库连接字符串
- 如果数据库服务名称不是 "Postgres"，请替换为实际名称

#### 步骤 3: 部署前端

1. 在项目中点击 **"+ New"** → **"GitHub Repo"** → 选择同一个仓库
2. 进入前端服务的 **Settings**：
   - **Root Directory** 设置为：`web`
3. 等待后端部署完成，复制后端 URL（在后端服务的 Settings → Domains）
4. 在前端的 **Variables** 添加：

```bash
NEXT_PUBLIC_API_BASE_URL=https://你的后端URL.railway.app
NEXT_TELEMETRY_DISABLED=1
SKIP_ENV_VALIDATION=1
```

#### 步骤 4: 更新 CORS（重要）

1. 等待前端部署完成，复制前端 URL
2. 回到**后端服务**的 **Variables**
3. 修改 `ALLOWED_ORIGINS`：
```bash
ALLOWED_ORIGINS=https://你的前端URL.railway.app
```

---

## ✅ 验证部署

### 1. 检查后端健康状态
```bash
curl https://你的后端URL.railway.app/health
```

**应该返回**：
```json
{
  "status": "healthy",
  "database": "healthy",
  "uptime_seconds": 123,
  ...
}
```

### 2. 访问前端
```
https://你的前端URL.railway.app
```

### 3. 完整测试
1. ✅ 注册新账号
2. ✅ 登录
3. ✅ 进行一次研究（输入任意问题）
4. ✅ 查看研究历史
5. ✅ 删除研究

---

## 🆘 常见问题

### Q: 后端部署失败，显示 "Cache mount ID" 错误
**A**: 已修复，重新部署即可。

### Q: 健康检查失败
**A**: 检查：
1. 环境变量是否正确配置
2. 查看 Railway 服务的 **Logs** 标签
3. 确认 `LANGGRAPH_CHECKPOINT_DB_URL` 设置正确

### Q: 前端无法连接后端
**A**: 检查：
1. `ALLOWED_ORIGINS` 包含前端完整 URL
2. `NEXT_PUBLIC_API_BASE_URL` 指向正确的后端 URL
3. 浏览器控制台是否有 CORS 错误

### Q: 数据库连接失败
**A**: 确认：
```bash
LANGGRAPH_CHECKPOINT_DB_URL=${{Postgres.DATABASE_URL}}
```
注意大小写，如果数据库服务叫 "postgres" 而不是 "Postgres"，需要相应修改。

---

## 📝 环境变量速查

| 变量 | 值 | 说明 |
|------|-----|------|
| `LANGGRAPH_CHECKPOINT_SAVER` | `true` | 启用数据库 |
| `LANGGRAPH_CHECKPOINT_DB_URL` | `${{Postgres.DATABASE_URL}}` | 数据库连接 |
| `JWT_SECRET_KEY` | 随机生成的密钥 | 安全密钥 |
| `ALLOWED_ORIGINS` | 前端 URL | CORS 设置 |
| `SEARCH_API` | `tavily` | 搜索引擎 |
| `TAVILY_API_KEY` | API Key | Tavily 密钥 |
| `NEXT_PUBLIC_API_BASE_URL` | 后端 URL | 前端配置 |

---

## 🎉 部署成功

全部步骤完成后，你的 DeerFlow 就可以供同事使用了！

- **前端地址**: `https://你的前端URL.railway.app`
- **后端 API**: `https://你的后端URL.railway.app`
- **API 文档**: `https://你的后端URL.railway.app/api/docs`

---

**预计部署时间**: 15-20 分钟  
**最后更新**: 2025-10-23


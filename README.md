# kingResearch 🦌

**企业级智能深度研究助手** - 基于多智能体协同的专业研究系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org/)
[![Railway Deploy](https://img.shields.io/badge/Railway-Deployed-blueviolet)](https://railway.app)

> **在线体验**: [https://kingresearch.up.railway.app](https://kingresearch.up.railway.app)

---

## 📋 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [技术架构](#技术架构)
- [快速开始](#快速开始)
- [部署指南](#部署指南)
- [使用说明](#使用说明)
- [成本优化](#成本优化)
- [项目结构](#项目结构)
- [贡献指南](#贡献指南)
- [开源协议](#开源协议)

---

## 🎯 项目简介

**kingResearch** 是基于 [DeerFlow](https://github.com/bytedance/deer-flow) 深度定制开发的企业级智能研究平台。通过多智能体协同、智能上下文管理和完整的用户系统，为研究人员提供专业级的深度研究能力。

### 为什么选择 kingResearch？

- 🤖 **多智能体协同** - 规划器、研究员、报告员三级分工，自动规划和执行复杂研究任务
- 🧠 **智能上下文压缩** - Summary 技术突破 100k+ token 限制，支持 20+ 步骤的深度研究
- 💬 **研究历史管理** - 完整的对话保存、回放与知识沉淀
- 🔐 **企业级认证** - JWT 用户登录、权限管理、配额控制
- 💡 **需求澄清系统** - 多轮对话精准理解复杂研究意图
- 📊 **成本优化** - 双模型策略降低 60% API 成本

---

## ✨ 核心特性

### 1. 多智能体协同研究

```
用户提问 → 规划器制定计划 → 多个研究员并行搜索 → 报告员综合分析 → 生成专业报告
```

- **Planner（规划器）**: 分析需求，制定研究步骤
- **Researcher（研究员）**: 并行执行搜索和信息收集
- **Reporter（报告员）**: 综合所有信息，生成结构化报告

### 2. 智能需求澄清

**自动识别模糊问题并进行多轮澄清：**

| 用户输入 | 系统行为 |
|---------|---------|
| "研究AI" | ❌ 模糊 → 询问具体技术、应用场景、时间范围 |
| "基于Transformer的AI视频合成技术优化研究" | ✅ 具体 → 直接开始研究 |

**智能规则：**
- 对已具体的主题跳过澄清，直接研究
- 最多 3 轮澄清，自动截断防止过度询问
- 支持中英文双语澄清

### 3. 研究历史与知识沉淀

- ✅ 自动保存每次研究的完整过程
- ✅ 支持回放研究过程，查看 AI 的思考路径
- ✅ 按用户隔离数据，支持多人使用
- ✅ 删除、导出研究记录

### 4. 上下文管理增强

**问题：** 深度研究需要多次搜索，上下文轻松超过 100k tokens

**解决方案：** 滚动摘要（Rolling Summary）
- 实时压缩已完成的研究步骤
- 保留最近 3 步原文，历史步骤使用摘要
- 上下文大小减少 70%，质量不下降

### 5. 成本优化策略

**双模型分工：**

| 任务类型 | 模型 | 价格 | 用途 |
|---------|------|------|------|
| 基础任务 | GPT-5-Nano | $0.10/1M tokens | 搜索查询生成、内容提取 |
| 推理任务 | Gemini 2.5 Pro | $1.25/1M tokens | 规划、分析、报告撰写 |

**效果：** 单次研究成本约 $0.055，相比纯 GPT-4 方案降低 **60%**

---

## 🏗️ 技术架构

### 后端技术栈

```
FastAPI (异步高性能 Web 框架)
├── LangGraph 0.3.5+ (多智能体编排)
├── PostgreSQL 16 (数据持久化)
├── JWT + Bcrypt (用户认证)
└── Tavily API (智能搜索引擎)
```

**核心依赖：**
- Python 3.12+
- LangGraph (状态机工作流)
- LangChain (LLM 抽象层)
- psycopg3 (异步 PostgreSQL 驱动)

### 前端技术栈

```
Next.js 15 (React 框架)
├── React 19 (UI 库)
├── TailwindCSS 4 (样式)
├── Zustand (状态管理)
├── SSE (实时流式通信)
└── next-intl (国际化)
```

### AI 模型

- **基础模型**: OpenAI GPT-5-Nano (via OpenRouter)
- **推理模型**: Google Gemini 2.5 Pro (via OpenRouter)
- **搜索引擎**: Tavily Search API

### 部署架构

```
Railway App (PaaS)
├── Backend Service (Python FastAPI)
├── Frontend Service (Next.js SSR)
└── PostgreSQL Database (Managed)
```

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- PostgreSQL 16+ (可选，用于数据持久化)
- pnpm 10+

### 1. 克隆项目

```bash
git clone https://github.com/your-username/kingresearch.git
cd kingresearch
```

### 2. 后端设置

```bash
# 安装 uv (Python 包管理器)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Keys
```

**必需的环境变量：**

```bash
# 数据库 (可选，不配置则不保存历史)
LANGGRAPH_CHECKPOINT_SAVER=true
LANGGRAPH_CHECKPOINT_DB_URL=postgresql://user:password@localhost:5432/kingresearch

# JWT 密钥
JWT_SECRET_KEY=your-secret-key-change-in-production

# AI 模型 (OpenRouter)
BASIC_MODEL__base_url=https://openrouter.ai/api/v1
BASIC_MODEL__model=openai/gpt-5-nano
BASIC_MODEL__api_key=your-openrouter-api-key

REASONING_MODEL__base_url=https://openrouter.ai/api/v1
REASONING_MODEL__model=google/gemini-2.5-pro
REASONING_MODEL__api_key=your-openrouter-api-key

# 搜索引擎
SEARCH_API=tavily
TAVILY_API_KEY=your-tavily-api-key
```

**启动后端：**

```bash
python server.py --host 0.0.0.0 --port 8000
```

### 3. 前端设置

```bash
cd web

# 安装依赖
pnpm install

# 配置环境变量
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api/" > .env.local
echo "SKIP_ENV_VALIDATION=true" >> .env.local

# 启动开发服务器
pnpm dev
```

访问 http://localhost:3000

---

## 📦 部署指南

### Railway 一键部署（推荐）

1. **Fork 本项目到你的 GitHub**

2. **创建 Railway 项目**
   - 访问 [railway.app](https://railway.app)
   - New Project → Deploy from GitHub
   - 选择你 fork 的仓库

3. **添加 PostgreSQL 数据库**
   - Add Service → PostgreSQL
   - 自动生成 `DATABASE_URL`

4. **配置后端环境变量**

```bash
# 数据库
LANGGRAPH_CHECKPOINT_SAVER=true
LANGGRAPH_CHECKPOINT_DB_URL=${{Postgres.DATABASE_URL}}

# 认证
JWT_SECRET_KEY=<生成随机密钥>
ALLOWED_ORIGINS=https://your-frontend-domain.up.railway.app

# AI 模型
BASIC_MODEL__api_key=<OpenRouter API Key>
REASONING_MODEL__api_key=<OpenRouter API Key>
TAVILY_API_KEY=<Tavily API Key>

# 其他
ENVIRONMENT=production
LOG_LEVEL=info
```

5. **配置前端环境变量**

```bash
NEXT_PUBLIC_API_URL=https://your-backend-domain.up.railway.app/api/
NODE_ENV=production
NEXT_TELEMETRY_DISABLED=1
```

6. **部署完成**
   - Railway 自动检测并部署
   - 等待 3-5 分钟
   - 访问生成的域名

### Docker 部署

```bash
# 构建镜像
docker build -t kingresearch-backend .
docker build -t kingresearch-frontend ./web

# 运行容器
docker-compose up -d
```

### 自建服务器部署

请参考 `docs/self-hosted-deployment.md`（待补充）

---

## 📖 使用说明

### 1. 用户注册与登录

**首次访问：**
1. 点击右上角"登录"按钮
2. 切换到"注册"标签
3. 输入用户名、邮箱、密码
4. 注册成功后自动登录

**已有账号：**
- 输入用户名和密码登录
- 勾选"记住我"可 30 天免登录

### 2. 开始研究

**基础用法：**

```
示例问题：
✅ "分析 2024 年 AI 大模型的技术发展趋势"
✅ "对比特斯拉和比亚迪的电动车技术路线"
✅ "量子计算的工作原理及应用前景"
```

**高级功能：**

- **报告风格** - 学术、科普、新闻、社媒、投资分析
- **深度思考** - 启用更强的推理模型（成本更高）
- **澄清功能** - 自动识别模糊问题并澄清
- **最大步骤数** - 控制研究深度（默认 3 步）

### 3. 查看研究历史

- 点击左侧边栏"历史记录"图标
- 按时间倒序查看所有研究
- 点击任意记录查看完整报告
- 点击"回放"查看研究过程

### 4. 最佳实践

**提问技巧：**
- ✅ 具体明确："2024 Q1 全球半导体市场分析"
- ✅ 包含约束："用通俗语言解释区块链，面向非技术人员"
- ❌ 过于宽泛："AI 是什么"
- ❌ 多个问题："AI 的历史、现状和未来"

**充分利用澄清：**
- 遇到澄清问题，认真回答
- 提供具体的范围、深度、角度要求
- 例如："我需要技术深度分析，面向工程师"

**善用研究历史：**
- 定期回顾历史研究，建立知识体系
- 相关主题的研究可以串联阅读
- 避免重复研究相同问题

---

## 💰 成本优化

### 当前成本结构

**搜索 API (Tavily):**
- 免费额度：1000 次/天/key
- 超额价格：$5/1000次

**LLM API (OpenRouter):**
- 单次研究成本：约 $0.055
- 月度成本（100 用户，5 次/天）：约 $825

### 已实现优化

- ✅ 双模型分工降低 60% 成本
- ✅ 上下文压缩减少 70% token 消耗
- ✅ 澄清机制避免无效研究
- ✅ 用户配额防止滥用

### 计划中优化（待实现）

**Tavily Key 池管理：**
- 配置多个 Tavily API Key
- 自动轮询和额度检测
- 单个 Key 超额时自动切换
- **预期效果：** 5 个 Key = 5000 次/天免费，搜索成本归零

---

## 📂 项目结构

```
kingresearch/
├── src/                          # 后端源码
│   ├── server/                   # FastAPI 服务
│   │   ├── app.py               # 主应用入口
│   │   ├── auth_request.py      # 认证请求模型
│   │   └── chat_request.py      # 聊天请求模型
│   ├── graph/                    # LangGraph 工作流
│   │   ├── nodes.py             # 节点定义
│   │   ├── builder.py           # 图构建器
│   │   ├── types.py             # 类型定义
│   │   └── checkpoint.py        # 检查点管理
│   ├── auth/                     # 认证模块
│   │   ├── jwt_handler.py       # JWT 处理
│   │   ├── password.py          # 密码加密
│   │   └── dependencies.py      # FastAPI 依赖
│   ├── llms/                     # LLM 抽象层
│   ├── tools/                    # 工具集
│   ├── prompts/                  # 提示词模板
│   └── config/                   # 配置管理
├── web/                          # 前端源码
│   ├── src/
│   │   ├── app/                 # Next.js App Router
│   │   │   ├── chat/           # 聊天页面
│   │   │   ├── auth/           # 登录注册页面
│   │   │   └── settings/       # 设置页面
│   │   ├── core/                # 核心功能
│   │   │   ├── api/            # API 调用
│   │   │   ├── auth/           # 认证上下文
│   │   │   ├── store/          # 状态管理
│   │   │   └── sse/            # 流式通信
│   │   └── components/          # UI 组件
│   └── public/                  # 静态资源
├── migrations/                   # 数据库迁移
├── tests/                        # 测试用例
├── pyproject.toml               # Python 项目配置
├── server.py                    # 服务器启动脚本
└── README.md                    # 项目文档
```

---

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 如何贡献

1. **Fork 本项目**
2. **创建特性分支** (`git checkout -b feature/AmazingFeature`)
3. **提交更改** (`git commit -m 'Add some AmazingFeature'`)
4. **推送到分支** (`git push origin feature/AmazingFeature`)
5. **提交 Pull Request**

### 代码规范

**后端 (Python):**
- 遵循 PEP 8 规范
- 使用 `ruff` 进行代码格式化
- 添加类型注解
- 编写单元测试

**前端 (TypeScript):**
- 遵循 ESLint 规则
- 使用 Prettier 格式化
- 组件使用 TypeScript
- 添加必要的注释

### 测试

```bash
# 后端测试
pytest

# 前端测试
cd web && pnpm test
```

---

## 🛣️ 路线图

### v1.0 (当前版本)
- ✅ 多智能体协同研究
- ✅ 用户认证与历史管理
- ✅ 智能需求澄清
- ✅ 上下文压缩优化
- ✅ Railway 部署支持

### v1.1 (计划中)
- 🔲 Tavily Key 池管理
- 🔲 DeepWiki 知识图谱生成
- 🔲 社区内容爬取（Reddit, 知乎, HN）
- 🔲 团队协作功能

### v2.0 (未来)
- 🔲 私有化部署一键安装
- 🔲 企业 SSO 集成
- 🔲 API 服务开放
- 🔲 自定义 Agent 能力

---

## 📄 开源协议

本项目基于 **MIT License** 开源。

```
Copyright (c) 2025 kingResearch Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```

查看 [LICENSE](LICENSE) 文件了解详情。

---

## 🙏 致谢

本项目基于以下优秀开源项目：

- [DeerFlow](https://github.com/bytedance/deer-flow) - 字节跳动开源的多智能体研究框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - LangChain 的图形工作流框架
- [Next.js](https://nextjs.org/) - Vercel 的 React 框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架

---

## 📞 联系方式

- **问题反馈**: [GitHub Issues](https://github.com/your-username/kingresearch/issues)
- **功能建议**: [GitHub Discussions](https://github.com/your-username/kingresearch/discussions)
- **在线体验**: [https://kingresearch.up.railway.app](https://kingresearch.up.railway.app)

---

<div align="center">

**如果觉得有帮助，请给个 ⭐ Star 支持一下！**

Made with ❤️ by kingResearch Team

</div>

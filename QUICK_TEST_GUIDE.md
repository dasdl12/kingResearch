# 🚀 快速测试指南

## 前端功能测试

### 1. 检查登录和历史按钮
访问 `http://localhost:3000`，在右上角应该看到：
- 🔑 **登录按钮**（LogIn图标）
- 💬 **研究历史按钮**（MessageSquareText图标）

### 2. 测试登录功能
1. 点击右上角的登录按钮，或直接访问 `http://localhost:3000/auth`
2. 在登录页面：
   - 点击 "Don't have an account? Sign up" 切换到注册模式
   - 填写用户名、邮箱、密码进行注册
   - 或使用已有账号登录

### 3. 测试研究历史功能
1. 登录后，点击右上角的研究历史按钮（💬图标）
2. 应该看到研究历史对话框
3. 如果没有完成的研究，会显示 "No completed researches yet"

### 4. 测试完整流程
1. 登录后开始一个新的研究
2. 等待研究完成（会显示最终报告）
3. 完成后，点击研究历史按钮应该能看到刚才的研究
4. 点击 "View" 按钮查看完整的研究报告

## 后端API测试

### 测试认证API
```bash
# 注册用户
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"123456","display_name":"Test User"}'

# 登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"123456"}'
```

### 测试研究历史API
```bash
# 获取用户研究历史（需要先登录获取token）
curl -X GET http://localhost:8000/api/researches \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 常见问题

### 如果看不到登录按钮
1. 检查浏览器控制台是否有错误
2. 确认前端服务正在运行：`pnpm dev`
3. 确认后端服务正在运行：`uv run server.py --reload`

### 如果登录失败
1. 检查后端是否正常运行
2. 检查数据库连接是否正常
3. 查看后端日志是否有错误

### 如果研究历史为空
1. 确保已经完成至少一个研究
2. 检查研究是否成功保存到数据库
3. 确认用户已登录

## 下一步
完成测试后，你可以：
1. 部署到生产环境
2. 添加更多功能（搜索、分类等）
3. 优化UI/UX
4. 添加更多安全措施





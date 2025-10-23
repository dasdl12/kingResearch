#!/usr/bin/env python3
"""
检查项目是否准备好部署到 Railway
运行: python scripts/check_railway_ready.py
"""

import os
import sys
from pathlib import Path

# 颜色代码
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_success(msg):
    print(f"{GREEN}✅ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}❌ {msg}{RESET}")

def print_warning(msg):
    print(f"{YELLOW}⚠️  {msg}{RESET}")

def print_info(msg):
    print(f"{BLUE}ℹ️  {msg}{RESET}")

def check_file_exists(filepath, required=True):
    """检查文件是否存在"""
    if Path(filepath).exists():
        print_success(f"找到文件: {filepath}")
        return True
    else:
        if required:
            print_error(f"缺少必需文件: {filepath}")
        else:
            print_warning(f"缺少可选文件: {filepath}")
        return False

def check_conf_yaml():
    """检查 conf.yaml 配置"""
    conf_path = Path("conf.yaml")
    if not conf_path.exists():
        print_error("conf.yaml 文件不存在！请复制 conf.yaml.example 并配置")
        return False
    
    # 读取配置检查是否包含 API key
    with open(conf_path, 'r') as f:
        content = f.read()
        if 'xxxx' in content or 'your-api-key' in content:
            print_warning("conf.yaml 中包含示例值，请替换为真实的 API Keys")
            return False
    
    print_success("conf.yaml 配置看起来正常")
    return True

def main():
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}🚂 Railway 部署准备检查{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    errors = []
    warnings = []
    
    # 检查项目根目录
    print(f"\n{BLUE}📁 检查项目文件...{RESET}")
    
    required_files = [
        "railway.json",
        "Dockerfile",
        "pyproject.toml",
        "server.py",
        "Procfile",
        ".env.example",
    ]
    
    for file in required_files:
        if not check_file_exists(file, required=True):
            errors.append(f"缺少必需文件: {file}")
    
    # 检查配置文件
    print(f"\n{BLUE}⚙️  检查配置文件...{RESET}")
    if not check_conf_yaml():
        errors.append("conf.yaml 配置未完成")
    
    # 检查前端文件
    print(f"\n{BLUE}🎨 检查前端文件...{RESET}")
    frontend_files = [
        "web/railway.json",
        "web/Dockerfile",
        "web/package.json",
        "web/next.config.js",
    ]
    
    for file in frontend_files:
        if not check_file_exists(file, required=True):
            errors.append(f"缺少前端文件: {file}")
    
    # 检查数据库迁移文件
    print(f"\n{BLUE}🗄️  检查数据库迁移文件...{RESET}")
    if not check_file_exists("migrations/001_create_users_and_add_user_id.sql"):
        errors.append("缺少数据库迁移文件")
    
    if not check_file_exists("scripts/init_railway_db.py"):
        errors.append("缺少数据库初始化脚本")
    
    # 检查关键源文件
    print(f"\n{BLUE}📝 检查源代码文件...{RESET}")
    source_files = [
        "src/server/app.py",
        "src/auth/jwt_handler.py",
        "src/graph/checkpoint.py",
    ]
    
    for file in source_files:
        check_file_exists(file, required=True)
    
    # 检查 .env.example
    print(f"\n{BLUE}🔑 检查环境变量模板...{RESET}")
    if Path(".env.example").exists():
        print_success(".env.example 存在")
        print_info("记得在 Railway 中配置所有必需的环境变量")
    else:
        warnings.append("缺少 .env.example 文件")
    
    # 打印总结
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}📊 检查总结{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    if not errors and not warnings:
        print_success("所有检查通过！项目已准备好部署到 Railway 🎉")
        print_info("\n下一步操作：")
        print("  1. 提交代码到 GitHub")
        print("  2. 访问 https://railway.app/")
        print("  3. 按照 QUICK_DEPLOY_RAILWAY.md 进行部署")
        return 0
    
    if errors:
        print(f"\n{RED}发现 {len(errors)} 个错误：{RESET}")
        for error in errors:
            print(f"  {RED}• {error}{RESET}")
    
    if warnings:
        print(f"\n{YELLOW}发现 {len(warnings)} 个警告：{RESET}")
        for warning in warnings:
            print(f"  {YELLOW}• {warning}{RESET}")
    
    if errors:
        print_error("\n请修复上述错误后再部署")
        return 1
    else:
        print_warning("\n存在警告，但可以继续部署")
        return 0

if __name__ == "__main__":
    sys.exit(main())


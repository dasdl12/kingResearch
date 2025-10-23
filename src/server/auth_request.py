# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Authentication related request and response models."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """User registration request."""

    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=6, description="Password")
    display_name: Optional[str] = Field(None, max_length=100, description="Display name")


class LoginRequest(BaseModel):
    """User login request."""

    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class AuthResponse(BaseModel):
    """Authentication response with token."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    display_name: Optional[str] = Field(None, description="Display name")


class UserInfo(BaseModel):
    """User information response."""

    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
    display_name: Optional[str] = Field(None, description="Display name")
    created_at: str = Field(..., description="Account creation timestamp")
    daily_quota: int = Field(..., description="Daily research quota")
    used_today: int = Field(..., description="Researches used today")









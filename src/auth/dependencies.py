# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""FastAPI dependency injection for authentication."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt_handler import verify_token

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Get current authenticated user ID (required).
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        User ID string
        
    Raises:
        HTTPException: If not authenticated or token invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload["sub"]  # Return user_id


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """Get current user ID if authenticated (optional).
    
    Used for endpoints that work both with and without authentication.
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        User ID string if authenticated, None otherwise
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = verify_token(token)
    return payload["sub"] if payload else None











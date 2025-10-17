# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Request and response models for conversation API.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    title: Optional[str] = Field(None, description="Conversation title")
    metadata: Optional[dict] = Field(None, description="Conversation metadata")


class UpdateConversationRequest(BaseModel):
    """Request to update a conversation."""

    title: Optional[str] = Field(None, description="Updated conversation title")
    metadata: Optional[dict] = Field(None, description="Updated conversation metadata")


class ConversationResponse(BaseModel):
    """Response for a single conversation."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    metadata: Optional[dict] = None


class ConversationListResponse(BaseModel):
    """Response for listing conversations."""

    conversations: List[ConversationResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Response for a single message."""

    id: str
    conversation_id: str
    role: str
    content: str
    agent: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: datetime


class MessageListResponse(BaseModel):
    """Response for listing messages."""

    messages: List[MessageResponse]
    total: int
    limit: int
    offset: int


class GenerateTitleRequest(BaseModel):
    """Request to generate conversation title."""

    first_message: str = Field(..., description="First user message in the conversation")


class GenerateTitleResponse(BaseModel):
    """Response for generated title."""

    title: str
    
    
class ExportConversationResponse(BaseModel):
    """Response for exporting a conversation."""
    
    conversation: ConversationResponse
    messages: List[MessageResponse]
    export_format: str  # "markdown" or "json"
    content: str



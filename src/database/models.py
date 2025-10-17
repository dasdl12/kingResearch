# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Database models for conversation and message persistence.
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from src.config.loader import get_str_env

logger = logging.getLogger(__name__)


class Message(BaseModel):
    """Message model."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    role: str  # "user", "assistant", "system"
    content: str
    agent: Optional[str] = None  # Which agent generated this message
    metadata: Optional[dict] = None  # Tool calls, images, etc.
    created_at: datetime = Field(default_factory=datetime.now)


class Conversation(BaseModel):
    """Conversation model."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = "New Conversation"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    message_count: int = 0
    metadata: Optional[dict] = None  # Settings, resources, etc.


def get_db_connection():
    """Get PostgreSQL database connection."""
    db_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "")
    
    if not db_url or not (db_url.startswith("postgresql://") or db_url.startswith("postgres://")):
        logger.warning(
            "No valid PostgreSQL connection URL found. "
            "Set LANGGRAPH_CHECKPOINT_DB_URL environment variable."
        )
        return None
    
    try:
        conn = psycopg.connect(db_url, row_factory=dict_row)
        logger.info("Successfully connected to PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return None


def init_database():
    """Initialize database tables."""
    conn = get_db_connection()
    if not conn:
        logger.error("Cannot initialize database: no connection available")
        return False
    
    try:
        with conn.cursor() as cursor:
            # Create conversations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    title VARCHAR(500) NOT NULL DEFAULT 'New Conversation',
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    message_count INTEGER NOT NULL DEFAULT 0,
                    metadata JSONB
                );
                
                CREATE INDEX IF NOT EXISTS idx_conversations_created_at 
                ON conversations(created_at DESC);
                
                CREATE INDEX IF NOT EXISTS idx_conversations_updated_at 
                ON conversations(updated_at DESC);
            """)
            
            # Create messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    agent VARCHAR(100),
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
                ON messages(conversation_id);
                
                CREATE INDEX IF NOT EXISTS idx_messages_created_at 
                ON messages(created_at);
                
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_created 
                ON messages(conversation_id, created_at);
            """)
            
            conn.commit()
            logger.info("Database tables initialized successfully")
            return True
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


class ConversationRepository:
    """Repository for conversation operations."""
    
    def __init__(self):
        self.conn = get_db_connection()
    
    def create_conversation(self, title: str = "New Conversation", metadata: Optional[dict] = None) -> Optional[Conversation]:
        """Create a new conversation."""
        if not self.conn:
            return None
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO conversations (title, metadata)
                    VALUES (%s, %s)
                    RETURNING id, title, created_at, updated_at, message_count, metadata
                    """,
                    (title, psycopg.types.json.Jsonb(metadata) if metadata else None)
                )
                row = cursor.fetchone()
                self.conn.commit()
                
                if row:
                    return Conversation(
                        id=str(row["id"]),
                        title=row["title"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        message_count=row["message_count"],
                        metadata=row["metadata"]
                    )
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
            self.conn.rollback()
        
        return None
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        if not self.conn:
            return None
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, title, created_at, updated_at, message_count, metadata
                    FROM conversations
                    WHERE id = %s
                    """,
                    (conversation_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    return Conversation(
                        id=str(row["id"]),
                        title=row["title"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        message_count=row["message_count"],
                        metadata=row["metadata"]
                    )
        except Exception as e:
            logger.error(f"Failed to get conversation: {e}")
        
        return None
    
    def list_conversations(self, limit: int = 50, offset: int = 0) -> List[Conversation]:
        """List conversations ordered by updated_at."""
        if not self.conn:
            return []
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, title, created_at, updated_at, message_count, metadata
                    FROM conversations
                    ORDER BY updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset)
                )
                rows = cursor.fetchall()
                
                return [
                    Conversation(
                        id=str(row["id"]),
                        title=row["title"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        message_count=row["message_count"],
                        metadata=row["metadata"]
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to list conversations: {e}")
            return []
    
    def update_conversation(self, conversation_id: str, title: Optional[str] = None, metadata: Optional[dict] = None) -> bool:
        """Update conversation title or metadata."""
        if not self.conn:
            return False
        
        try:
            with self.conn.cursor() as cursor:
                updates = []
                params = []
                
                if title is not None:
                    updates.append("title = %s")
                    params.append(title)
                
                if metadata is not None:
                    updates.append("metadata = %s")
                    params.append(psycopg.types.json.Jsonb(metadata))
                
                if not updates:
                    return True
                
                updates.append("updated_at = NOW()")
                params.append(conversation_id)
                
                query = f"""
                    UPDATE conversations
                    SET {", ".join(updates)}
                    WHERE id = %s
                """
                
                cursor.execute(query, params)
                self.conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Failed to update conversation: {e}")
            self.conn.rollback()
            return False
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages and chat_streams."""
        if not self.conn:
            return False
        
        try:
            with self.conn.cursor() as cursor:
                # Delete from chat_streams table (using conversation_id as thread_id)
                cursor.execute(
                    "DELETE FROM chat_streams WHERE thread_id = %s",
                    (conversation_id,)
                )
                chat_streams_deleted = cursor.rowcount
                
                # Delete from conversations table (this will cascade delete messages)
                cursor.execute(
                    "DELETE FROM conversations WHERE id = %s",
                    (conversation_id,)
                )
                conversation_deleted = cursor.rowcount > 0
                
                self.conn.commit()
                logger.info(f"🗑️ [DEBUG] Deleted conversation {conversation_id}: "
                           f"chat_streams={chat_streams_deleted}, conversation={conversation_deleted}")
                return conversation_deleted
        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}")
            self.conn.rollback()
            return False
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


class MessageRepository:
    """Repository for message operations."""
    
    def __init__(self):
        self.conn = get_db_connection()
    
    def add_message(self, message: Message) -> bool:
        """Add a message to a conversation."""
        if not self.conn:
            return False
        
        try:
            with self.conn.cursor() as cursor:
                # Insert message
                cursor.execute(
                    """
                    INSERT INTO messages (id, conversation_id, role, content, agent, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        message.id,
                        message.conversation_id,
                        message.role,
                        message.content,
                        message.agent,
                        psycopg.types.json.Jsonb(message.metadata) if message.metadata else None,
                        message.created_at
                    )
                )
                
                # Update conversation message count and updated_at
                cursor.execute(
                    """
                    UPDATE conversations
                    SET message_count = message_count + 1,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (message.conversation_id,)
                )
                
                self.conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            self.conn.rollback()
            return False
    
    def get_messages(self, conversation_id: str, limit: int = 100, offset: int = 0) -> List[Message]:
        """Get messages for a conversation."""
        if not self.conn:
            return []
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, conversation_id, role, content, agent, metadata, created_at
                    FROM messages
                    WHERE conversation_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s OFFSET %s
                    """,
                    (conversation_id, limit, offset)
                )
                rows = cursor.fetchall()
                
                return [
                    Message(
                        id=str(row["id"]),
                        conversation_id=str(row["conversation_id"]),
                        role=row["role"],
                        content=row["content"],
                        agent=row["agent"],
                        metadata=row["metadata"],
                        created_at=row["created_at"]
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return []
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import time
import uuid
from datetime import datetime
from functools import wraps
from typing import List, Optional, Tuple

import psycopg
from langgraph.store.memory import InMemoryStore
from psycopg.rows import dict_row
from pymongo import MongoClient

from src.config.loader import get_bool_env, get_int_env, get_str_env

logger = logging.getLogger(__name__)


def retry_on_db_error(max_retries: int = 3, delay: float = 1.0):
    """
    Decorator to retry database operations on connection errors.
    
    Args:
        max_retries: Maximum number of retry attempts (from env DB_MAX_RETRIES or default 3)
        delay: Initial delay between retries in seconds (exponential backoff)
    """
    # Allow override from environment
    max_retries = get_int_env("DB_MAX_RETRIES", max_retries)
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"Database operation failed (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Database operation failed after {max_retries} attempts: {e}")
                except Exception as e:
                    # Don't retry on non-connection errors
                    logger.error(f"Non-retryable database error: {e}")
                    raise
            raise last_exception
        return wrapper
    return decorator


class ChatStreamManager:
    """
    Manages chat stream messages with persistent storage and in-memory caching.

    This class handles the storage and retrieval of chat messages using both
    an in-memory store for temporary data and MongoDB or PostgreSQL for persistent storage.
    It tracks message chunks and consolidates them when a conversation finishes.

    Attributes:
        store (InMemoryStore): In-memory storage for temporary message chunks
        mongo_client (MongoClient): MongoDB client connection
        mongo_db (Database): MongoDB database instance
        postgres_conn (psycopg.Connection): PostgreSQL connection
        logger (logging.Logger): Logger instance for this class
    """

    def __init__(
        self, checkpoint_saver: bool = False, db_uri: Optional[str] = None
    ) -> None:
        """
        Initialize the ChatStreamManager with database connections.

        Args:
            db_uri: Database connection URI. Supports MongoDB (mongodb://) and PostgreSQL (postgresql://)
                   If None, uses LANGGRAPH_CHECKPOINT_DB_URL env var or defaults to localhost
        """
        self.logger = logging.getLogger(__name__)
        self.store = InMemoryStore()
        self.checkpoint_saver = checkpoint_saver
        # Use provided URI or fall back to environment variable or default
        self.db_uri = db_uri

        # Initialize database connections
        self.mongo_client = None
        self.mongo_db = None
        self.postgres_conn = None

        if self.checkpoint_saver:
            if self.db_uri.startswith("mongodb://"):
                self._init_mongodb()
            elif self.db_uri.startswith("postgresql://") or self.db_uri.startswith(
                "postgres://"
            ):
                self._init_postgresql()
            else:
                self.logger.warning(
                    f"Unsupported database URI scheme: {self.db_uri}. "
                    "Supported schemes: mongodb://, postgresql://, postgres://"
                )
        else:
            self.logger.warning("Checkpoint saver is disabled")

    def _init_mongodb(self) -> None:
        """Initialize MongoDB connection."""

        try:
            self.mongo_client = MongoClient(self.db_uri)
            self.mongo_db = self.mongo_client.checkpointing_db
            # Test connection
            self.mongo_client.admin.command("ping")
            self.logger.info("Successfully connected to MongoDB")
        except Exception as e:
            self.logger.error(f"Failed to connect to MongoDB: {e}")

    def _init_postgresql(self) -> None:
        """Initialize PostgreSQL connection and create tables if needed."""

        try:
            # Add SSL mode and connection parameters to connection URL
            db_uri = self.db_uri
            
            # Get connection parameters from environment or use defaults
            from src.config.loader import get_int_env
            connect_timeout = get_int_env("DB_CONNECT_TIMEOUT", 60)
            keepalives_idle = get_int_env("DB_KEEPALIVES_IDLE", 30)
            keepalives_interval = get_int_env("DB_KEEPALIVES_INTERVAL", 10)
            keepalives_count = get_int_env("DB_KEEPALIVES_COUNT", 5)
            
            # Build connection parameters
            params = []
            if "sslmode" not in db_uri:
                params.append("sslmode=require")
                self.logger.info("Added sslmode=require to PostgreSQL connection URL")
            
            # Add connection stability parameters
            params.extend([
                f"connect_timeout={connect_timeout}",
                "keepalives=1",
                f"keepalives_idle={keepalives_idle}",
                f"keepalives_interval={keepalives_interval}",
                f"keepalives_count={keepalives_count}"
            ])
            
            separator = "&" if "?" in db_uri else "?"
            db_uri = f"{db_uri}{separator}" + "&".join(params)
            
            self.postgres_conn = psycopg.connect(db_uri, row_factory=dict_row)
            self.logger.info("Successfully connected to PostgreSQL with enhanced stability settings")
            self._create_users_table()
            self._create_chat_streams_table()
            self._create_research_replays_table()
        except Exception as e:
            self.logger.error(f"Failed to connect to PostgreSQL: {e}")

    def _create_users_table(self) -> None:
        """Create the users table if it doesn't exist."""
        try:
            with self.postgres_conn.cursor() as cursor:
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
                
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
                """
                cursor.execute(create_table_sql)
                self.postgres_conn.commit()
                self.logger.info("Users table created/verified successfully")
        except Exception as e:
            self.logger.error(f"Failed to create users table: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()

    def _create_chat_streams_table(self) -> None:
        """Create the chat_streams table if it doesn't exist."""
        try:
            with self.postgres_conn.cursor() as cursor:
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS chat_streams (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    thread_id VARCHAR(255) NOT NULL UNIQUE,
                    messages JSONB NOT NULL,
                    ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_chat_streams_thread_id ON chat_streams(thread_id);
                CREATE INDEX IF NOT EXISTS idx_chat_streams_ts ON chat_streams(ts);
                """
                cursor.execute(create_table_sql)
                self.postgres_conn.commit()
                self.logger.info("Chat streams table created/verified successfully")
        except Exception as e:
            self.logger.error(f"Failed to create chat_streams table: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()

    def _create_research_replays_table(self) -> None:
        """Create the research_replays table if it doesn't exist."""
        try:
            with self.postgres_conn.cursor() as cursor:
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS research_replays (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    thread_id VARCHAR(255) NOT NULL,
                    user_id UUID,
                    research_topic VARCHAR(500) NOT NULL,
                    report_style VARCHAR(50) NOT NULL,
                    final_report TEXT,
                    observations JSONB,
                    plan JSONB,
                    is_completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    completed_at TIMESTAMP WITH TIME ZONE,
                    ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_research_replays_thread_id ON research_replays(thread_id);
                CREATE INDEX IF NOT EXISTS idx_research_replays_user_id ON research_replays(user_id);
                CREATE INDEX IF NOT EXISTS idx_research_replays_is_completed ON research_replays(is_completed);
                CREATE INDEX IF NOT EXISTS idx_research_replays_user_completed ON research_replays(user_id, is_completed);
                CREATE INDEX IF NOT EXISTS idx_research_replays_ts ON research_replays(ts);
                """
                cursor.execute(create_table_sql)
                self.postgres_conn.commit()
                self.logger.info("Research replays table created/verified successfully")
        except Exception as e:
            self.logger.error(f"Failed to create research_replays table: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()

    def process_stream_message(
        self, thread_id: str, message: str, finish_reason: str
    ) -> bool:
        """
        Process and store a chat stream message chunk.

        This method handles individual message chunks during streaming and consolidates
        them into a complete message when the stream finishes. Messages are stored
        temporarily in memory and permanently in MongoDB when complete.

        Args:
            thread_id: Unique identifier for the conversation thread
            message: The message content or chunk to store
            finish_reason: Reason for message completion ("stop", "interrupt", or partial)

        Returns:
            bool: True if message was processed successfully, False otherwise
        """
        if not thread_id or not isinstance(thread_id, str):
            self.logger.warning("Invalid thread_id provided")
            return False

        if not message:
            self.logger.warning("Empty message provided")
            return False

        try:
            # Create namespace for this thread's messages
            store_namespace: Tuple[str, str] = ("messages", thread_id)

            # Get or initialize message cursor for tracking chunks
            cursor = self.store.get(store_namespace, "cursor")
            current_index = 0

            if cursor is None:
                # Initialize cursor for new conversation
                self.store.put(store_namespace, "cursor", {"index": 0})
            else:
                # Increment index for next chunk
                current_index = int(cursor.value.get("index", 0)) + 1
                self.store.put(store_namespace, "cursor", {"index": current_index})

            # Store the current message chunk
            self.store.put(store_namespace, f"chunk_{current_index}", message)

            # Check if conversation is complete and should be persisted
            if finish_reason in ("stop", "interrupt"):
                return self._persist_complete_conversation(
                    thread_id, store_namespace, current_index
                )

            return True

        except Exception as e:
            self.logger.error(
                f"Error processing stream message for thread {thread_id}: {e}"
            )
            return False

    def _persist_complete_conversation(
        self, thread_id: str, store_namespace: Tuple[str, str], final_index: int
    ) -> bool:
        """
        Persist completed conversation to database (MongoDB or PostgreSQL).

        Retrieves all message chunks from memory store and saves the complete
        conversation to the configured database for permanent storage.

        Args:
            thread_id: Unique identifier for the conversation thread
            store_namespace: Namespace tuple for accessing stored messages
            final_index: The final chunk index for this conversation

        Returns:
            bool: True if persistence was successful, False otherwise
        """
        try:
            # Retrieve all message chunks from memory store
            # Get all messages up to the final index including cursor metadata
            memories = self.store.search(store_namespace, limit=final_index + 2)

            # Extract message content, filtering out cursor metadata
            messages: List[str] = []
            for item in memories:
                value = item.dict().get("value", "")
                # Skip cursor metadata, only include actual message chunks
                if value and not isinstance(value, dict):
                    messages.append(str(value))

            if not messages:
                self.logger.warning(f"No messages found for thread {thread_id}")
                return False

            if not self.checkpoint_saver:
                self.logger.warning("Checkpoint saver is disabled")
                return False

            # Choose persistence method based on available connection
            if self.mongo_db is not None:
                return self._persist_to_mongodb(thread_id, messages)
            elif self.postgres_conn is not None:
                return self._persist_to_postgresql(thread_id, messages)
            else:
                self.logger.warning("No database connection available")
                return False

        except Exception as e:
            self.logger.error(
                f"Error persisting conversation for thread {thread_id}: {e}"
            )
            return False

    def _persist_to_mongodb(self, thread_id: str, messages: List[str]) -> bool:
        """Persist conversation to MongoDB."""
        try:
            # Get MongoDB collection for chat streams
            collection = self.mongo_db.chat_streams

            # Check if conversation already exists in database
            existing_document = collection.find_one({"thread_id": thread_id})

            current_timestamp = datetime.now()

            if existing_document:
                # Update existing conversation with new messages
                update_result = collection.update_one(
                    {"thread_id": thread_id},
                    {"$set": {"messages": messages, "ts": current_timestamp}},
                )
                self.logger.info(
                    f"Updated conversation for thread {thread_id}: "
                    f"{update_result.modified_count} documents modified"
                )
                return update_result.modified_count > 0
            else:
                # Create new conversation document
                new_document = {
                    "thread_id": thread_id,
                    "messages": messages,
                    "ts": current_timestamp,
                    "id": uuid.uuid4().hex,
                }
                insert_result = collection.insert_one(new_document)
                self.logger.info(
                    f"Created new conversation: {insert_result.inserted_id}"
                )
                return insert_result.inserted_id is not None

        except Exception as e:
            self.logger.error(f"Error persisting to MongoDB: {e}")
            return False

    def _persist_to_postgresql(self, thread_id: str, messages: List[str]) -> bool:
        """Persist conversation to PostgreSQL."""
        try:
            with self.postgres_conn.cursor() as cursor:
                # Check if conversation already exists
                cursor.execute(
                    "SELECT id FROM chat_streams WHERE thread_id = %s", (thread_id,)
                )
                existing_record = cursor.fetchone()

                current_timestamp = datetime.now()
                messages_json = json.dumps(messages)

                if existing_record:
                    # Update existing conversation with new messages
                    cursor.execute(
                        """
                        UPDATE chat_streams 
                        SET messages = %s, ts = %s 
                        WHERE thread_id = %s
                        """,
                        (messages_json, current_timestamp, thread_id),
                    )
                    affected_rows = cursor.rowcount
                    self.postgres_conn.commit()

                    self.logger.info(
                        f"Updated conversation for thread {thread_id}: "
                        f"{affected_rows} rows modified"
                    )
                    return affected_rows > 0
                else:
                    # Create new conversation record
                    conversation_id = uuid.uuid4()
                    cursor.execute(
                        """
                        INSERT INTO chat_streams (id, thread_id, messages, ts) 
                        VALUES (%s, %s, %s, %s)
                        """,
                        (conversation_id, thread_id, messages_json, current_timestamp),
                    )
                    affected_rows = cursor.rowcount
                    self.postgres_conn.commit()

                    self.logger.info(
                        f"Created new conversation with ID: {conversation_id}"
                    )
                    return affected_rows > 0

        except Exception as e:
            self.logger.error(f"Error persisting to PostgreSQL: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()
            return False

    def close(self) -> None:
        """Close database connections."""
        try:
            if self.mongo_client is not None:
                self.mongo_client.close()
                self.logger.info("MongoDB connection closed")
        except Exception as e:
            self.logger.error(f"Error closing MongoDB connection: {e}")

        try:
            if self.postgres_conn is not None:
                self.postgres_conn.close()
                self.logger.info("PostgreSQL connection closed")
        except Exception as e:
            self.logger.error(f"Error closing PostgreSQL connection: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connections."""
        self.close()

    def save_completed_research(
        self,
        thread_id: str,
        user_id: Optional[str],
        research_topic: str,
        report_style: str,
        final_report: str,
        observations: Optional[List[str]] = None,
        current_plan: Optional[dict] = None,
    ) -> bool:
        """
        Save a completed research with full process data.
        
        IMPORTANT: This function should ONLY be called when final_report is available.
        Saves the complete research process including observations and plan for direct viewing.
        
        Args:
            thread_id: Unique identifier for the conversation thread
            user_id: User ID who initiated the research (can be None for backward compatibility)
            research_topic: The research topic/question
            report_style: Report writing style
            final_report: The completed final report content
            observations: List of research observations/activities (research process steps)
            current_plan: The research plan that was executed
            
        Returns:
            bool: True if saved successfully
        """
        if not final_report or not final_report.strip():
            self.logger.warning(f"Empty final_report for thread {thread_id}, skipping save")
            return False
        
        if not self.checkpoint_saver:
            self.logger.warning("Checkpoint saver is disabled")
            return False
        
        try:
            current_time = datetime.now()
            
            # Prepare observations and plan data
            observations_json = json.dumps(observations or [], ensure_ascii=False)
            plan_json = json.dumps(current_plan or {}, ensure_ascii=False)
            
            if self.postgres_conn is not None:
                with self.postgres_conn.cursor() as cursor:
                    # Check if research already exists
                    cursor.execute(
                        "SELECT id, is_completed FROM research_replays WHERE thread_id = %s",
                        (thread_id,),
                    )
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Update existing research with complete data
                        cursor.execute(
                            """
                            UPDATE research_replays 
                            SET user_id = %s,
                                final_report = %s, 
                                observations = %s,
                                plan = %s,
                                is_completed = TRUE,
                                completed_at = %s,
                                ts = %s
                            WHERE thread_id = %s
                            """,
                            (user_id, final_report, observations_json, plan_json, current_time, current_time, thread_id),
                        )
                        self.logger.info(f"Updated completed research for thread {thread_id}")
                    else:
                        # Insert new completed research
                        cursor.execute(
                            """
                            INSERT INTO research_replays 
                            (thread_id, user_id, research_topic, report_style, final_report, 
                             observations, plan, is_completed, completed_at, ts)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
                            """,
                            (thread_id, user_id, research_topic, report_style, final_report,
                             observations_json, plan_json, current_time, current_time),
                        )
                        self.logger.info(f"Saved completed research for thread {thread_id}")
                    
                    self.postgres_conn.commit()
                    
                    # Increment user usage if user_id provided
                    if user_id:
                        self._increment_user_usage(user_id)
                    
                    return True
            elif self.mongo_db is not None:
                collection = self.mongo_db.research_replays
                
                existing = collection.find_one({"thread_id": thread_id})
                if existing:
                    collection.update_one(
                        {"thread_id": thread_id},
                        {
                            "$set": {
                                "user_id": user_id,
                                "final_report": final_report,
                                "observations": observations or [],
                                "plan": current_plan or {},
                                "is_completed": True,
                                "completed_at": current_time,
                                "ts": current_time,
                            }
                        },
                    )
                else:
                    collection.insert_one({
                        "id": uuid.uuid4().hex,
                        "thread_id": thread_id,
                        "user_id": user_id,
                        "research_topic": research_topic,
                        "report_style": report_style,
                        "final_report": final_report,
                        "observations": observations or [],
                        "plan": current_plan or {},
                        "is_completed": True,
                        "completed_at": current_time,
                        "ts": current_time,
                    })
                
                self.logger.info(f"Saved completed research to MongoDB for thread {thread_id}")
                return True
            else:
                self.logger.warning("No database connection available")
                return False
                
        except Exception as e:
            self.logger.error(f"Error saving completed research: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()
            return False
    
    def _increment_user_usage(self, user_id: str) -> None:
        """Increment user's daily usage count."""
        try:
            with self.postgres_conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET used_today = used_today + 1,
                        updated_at = NOW()
                    WHERE id = %s AND last_reset_date = CURRENT_DATE
                    """,
                    (user_id,),
                )
                self.postgres_conn.commit()
        except Exception as e:
            self.logger.error(f"Error incrementing user usage: {e}")
    
    def get_user_researches(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> List[dict]:
        """
        Get completed researches for a specific user (list view, without full report).
        
        Args:
            user_id: User ID
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            List of completed research records (metadata only, no full report/observations)
        """
        try:
            if self.postgres_conn is not None:
                with self.postgres_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, thread_id, research_topic, report_style, 
                               is_completed, created_at, completed_at, ts
                        FROM research_replays
                        WHERE user_id = %s AND is_completed = TRUE
                        ORDER BY completed_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (user_id, limit, offset),
                    )
                    results = cursor.fetchall()
                    return [dict(row) for row in results]
            elif self.mongo_db is not None:
                collection = self.mongo_db.research_replays
                cursor = (
                    collection.find(
                        {"user_id": user_id, "is_completed": True},
                        {"final_report": 0, "observations": 0, "plan": 0}  # Exclude large fields
                    )
                    .sort("completed_at", -1)
                    .limit(limit)
                    .skip(offset)
                )
                return list(cursor)
            else:
                return []
        except Exception as e:
            self.logger.error(f"Error getting user researches: {e}")
            return []
    
    def get_research_report(self, thread_id: str, user_id: Optional[str] = None) -> Optional[dict]:
        """
        Get a completed research report with FULL data (observations, plan, final_report).
        
        This is used when user clicks on a history item to view the complete research.
        
        Args:
            thread_id: Thread ID
            user_id: Optional user ID for access control
            
        Returns:
            Complete research record with final_report, observations, and plan, or None if not found
        """
        try:
            if self.postgres_conn is not None:
                with self.postgres_conn.cursor() as cursor:
                    if user_id:
                        # Verify ownership
                        cursor.execute(
                            """
                            SELECT id, thread_id, research_topic, report_style, 
                                   final_report, observations, plan,
                                   is_completed, created_at, completed_at, ts
                            FROM research_replays
                            WHERE thread_id = %s AND user_id = %s AND is_completed = TRUE
                            """,
                            (thread_id, user_id),
                        )
                    else:
                        # No ownership check (backward compatibility)
                        cursor.execute(
                            """
                            SELECT id, thread_id, research_topic, report_style, 
                                   final_report, observations, plan,
                                   is_completed, created_at, completed_at, ts
                            FROM research_replays
                            WHERE thread_id = %s AND is_completed = TRUE
                            """,
                            (thread_id,),
                        )
                    result = cursor.fetchone()
                    if result:
                        data = dict(result)
                        # Parse JSON fields
                        if data.get('observations') and isinstance(data['observations'], str):
                            data['observations'] = json.loads(data['observations'])
                        if data.get('plan') and isinstance(data['plan'], str):
                            data['plan'] = json.loads(data['plan'])
                        return data
                    return None
            elif self.mongo_db is not None:
                collection = self.mongo_db.research_replays
                query = {"thread_id": thread_id, "is_completed": True}
                if user_id:
                    query["user_id"] = user_id
                return collection.find_one(query)
            else:
                return None
        except Exception as e:
            self.logger.error(f"Error getting research report: {e}")
            return None
    
    def delete_research(self, thread_id: str, user_id: str) -> bool:
        """
        Delete a research (with ownership verification).
        
        Args:
            thread_id: Thread ID
            user_id: User ID (for ownership check)
            
        Returns:
            True if deleted successfully
        """
        try:
            if self.postgres_conn is not None:
                with self.postgres_conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM research_replays WHERE thread_id = %s AND user_id = %s",
                        (thread_id, user_id),
                    )
                    deleted = cursor.rowcount > 0
                    self.postgres_conn.commit()
                    return deleted
            elif self.mongo_db is not None:
                collection = self.mongo_db.research_replays
                result = collection.delete_one({"thread_id": thread_id, "user_id": user_id})
                return result.deleted_count > 0
            else:
                return False
        except Exception as e:
            self.logger.error(f"Error deleting research: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()
            return False


# Global instance for backward compatibility
# TODO: Consider using dependency injection instead of global instance
_default_manager = ChatStreamManager(
    checkpoint_saver=get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False),
    db_uri=get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "mongodb://localhost:27017"),
)


def chat_stream_message(thread_id: str, message: str, finish_reason: str) -> bool:
    """
    Legacy function wrapper for backward compatibility.

    Args:
        thread_id: Unique identifier for the conversation thread
        message: The message content to store
        finish_reason: Reason for message completion

    Returns:
        bool: True if message was processed successfully
    """
    checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
    if checkpoint_saver:
        return _default_manager.process_stream_message(
            thread_id, message, finish_reason
        )
    else:
        return False


def save_completed_research(
    thread_id: str,
    user_id: Optional[str],
    research_topic: str,
    report_style: str,
    final_report: str,
    observations: Optional[List[str]] = None,
    current_plan: Optional[dict] = None,
) -> bool:
    """Save a completed research report with full process data (only when final_report is available)."""
    checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
    if checkpoint_saver:
        return _default_manager.save_completed_research(
            thread_id, user_id, research_topic, report_style, final_report,
            observations, current_plan
        )
    return False


def get_user_researches(user_id: str, limit: int = 20, offset: int = 0) -> List[dict]:
    """Get user's completed researches."""
    checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
    if checkpoint_saver:
        return _default_manager.get_user_researches(user_id, limit, offset)
    return []


def get_research_report(thread_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    """Get a completed research report."""
    checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
    if checkpoint_saver:
        return _default_manager.get_research_report(thread_id, user_id)
    return None


def delete_research(thread_id: str, user_id: str) -> bool:
    """Delete a research."""
    checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
    if checkpoint_saver:
        return _default_manager.delete_research(thread_id, user_id)
    return False

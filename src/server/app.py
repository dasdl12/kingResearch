# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import base64
import json
import logging
import os
from typing import Annotated, Any, List, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langgraph.checkpoint.mongodb import AsyncMongoDBSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
import psycopg
from psycopg_pool import AsyncConnectionPool

from src.config.configuration import get_recursion_limit
from src.config.loader import get_bool_env, get_str_env
from src.config.report_style import ReportStyle
from src.config.tools import SELECTED_RAG_PROVIDER
from src.auth.dependencies import get_current_user, get_current_user_optional
from src.auth.jwt_handler import create_access_token
from src.auth.password import hash_password, verify_password
from src.graph.builder import build_graph_with_memory
from src.graph.checkpoint import (
    chat_stream_message,
    delete_research,
    get_research_report,
    get_user_researches,
)
from src.llms.llm import get_configured_llm_models
from src.podcast.graph.builder import build_graph as build_podcast_graph
from src.ppt.graph.builder import build_graph as build_ppt_graph
from src.prompt_enhancer.graph.builder import build_graph as build_prompt_enhancer_graph
from src.prose.graph.builder import build_graph as build_prose_graph
from src.rag.builder import build_retriever
from src.rag.milvus import load_examples
from src.rag.retriever import Resource
from src.server.chat_request import (
    ChatRequest,
    EnhancePromptRequest,
    GeneratePodcastRequest,
    GeneratePPTRequest,
    GenerateProseRequest,
    TTSRequest,
)
from src.server.config_request import ConfigResponse
from src.server.mcp_request import MCPServerMetadataRequest, MCPServerMetadataResponse
from src.server.mcp_utils import load_mcp_tools
from src.server.auth_request import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserInfo,
)
from src.server.rag_request import (
    RAGConfigResponse,
    RAGResourceRequest,
    RAGResourcesResponse,
)
from src.tools import VolcengineTTS
from src.utils.json_utils import sanitize_args
from datetime import datetime
import time

logger = logging.getLogger(__name__)

# Application startup time for metrics
start_time = time.time()

# Configure Windows event loop policy for PostgreSQL compatibility
# On Windows, psycopg requires a selector-based event loop, not the default ProactorEventLoop
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

INTERNAL_SERVER_ERROR_DETAIL = "Internal Server Error"

app = FastAPI(
    title="DeerFlow API",
    description="API for Deer",
    version="0.1.0",
)

# Add CORS middleware
# It's recommended to load the allowed origins from an environment variable
# for better security and flexibility across different environments.
allowed_origins_str = get_str_env("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

logger.info(f"Allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Restrict to specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Use the configured list of methods
    allow_headers=["*"],  # Now allow all headers, but can be restricted further
)

# Load examples into Milvus if configured
load_examples()

in_memory_store = InMemoryStore()
graph = build_graph_with_memory()


# Startup event to initialize database
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info("Application startup - initializing database...")
    
    try:
        db_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "")
        checkpoint_enabled = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
        
        if checkpoint_enabled and db_url and db_url.startswith("postgresql://"):
            logger.info("Checking database tables...")
            
            # Add SSL mode to connection URL if not already present (required for Railway)
            if "sslmode" not in db_url:
                separator = "&" if "?" in db_url else "?"
                db_url = f"{db_url}{separator}sslmode=require"
                logger.info("Added sslmode=require to PostgreSQL connection URL")
            
            from pathlib import Path
            migrations_dir = Path(__file__).parent.parent.parent / "migrations"
            
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    # Check if tables exist
                    cur.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name IN ('users', 'research_replays')
                    """)
                    existing_tables = [row[0] for row in cur.fetchall()]
                    
                    if 'users' in existing_tables and 'research_replays' in existing_tables:
                        logger.info("✅ Database tables already exist")
                    else:
                        logger.info("📝 Creating database tables...")
                        
                        # Run migrations
                        for migration_file in sorted(migrations_dir.glob("*.sql")):
                            logger.info(f"Running migration: {migration_file.name}")
                            with open(migration_file, 'r', encoding='utf-8') as f:
                                sql = f.read()
                            cur.execute(sql)
                            conn.commit()
                        
                        logger.info("✅ Database initialization completed")
        else:
            logger.info("Database checkpoint not enabled or not PostgreSQL")
            
    except Exception as e:
        logger.error(f"Database initialization failed (non-fatal): {e}")
        logger.info("Application will continue without database persistence")
    
    logger.info("✅ Application startup complete")


@app.get("/")
async def root():
    """Root endpoint - API status check."""
    return {
        "name": "DeerFlow API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/api/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway and monitoring."""
    try:
        # Check database connection if configured
        checkpoint_enabled = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
        db_status = "not_configured"
        
        if checkpoint_enabled:
            db_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "")
            if db_url:
                try:
                    if db_url.startswith("postgresql://"):
                        with psycopg.connect(db_url, connect_timeout=5) as conn:
                            with conn.cursor() as cur:
                                cur.execute("SELECT 1")
                        db_status = "healthy"
                    elif db_url.startswith("mongodb://"):
                        db_status = "healthy"  # MongoDB check would need async mongo client
                except Exception as e:
                    logger.error(f"Database health check failed: {e}")
                    db_status = "unhealthy"
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "0.1.0",
            "uptime_seconds": int(time.time() - start_time),
            "database": db_status,
            "environment": get_str_env("ENVIRONMENT", "development")
        }
    except Exception as e:
        logger.exception(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user_id: str | None = Depends(get_current_user_optional),
):
    # Check if MCP server configuration is enabled
    mcp_enabled = get_bool_env("ENABLE_MCP_SERVER_CONFIGURATION", False)

    # Validate MCP settings if provided
    if request.mcp_settings and not mcp_enabled:
        raise HTTPException(
            status_code=403,
            detail="MCP server configuration is disabled. Set ENABLE_MCP_SERVER_CONFIGURATION=true to enable MCP features.",
        )

    thread_id = request.thread_id
    if thread_id == "__default__":
        thread_id = str(uuid4())

    return StreamingResponse(
        _astream_workflow_generator(
            request.model_dump()["messages"],
            thread_id,
            request.resources,
            request.max_plan_iterations,
            request.max_step_num,
            request.max_search_results,
            request.auto_accepted_plan,
            request.interrupt_feedback,
            request.mcp_settings if mcp_enabled else {},
            request.enable_background_investigation,
            request.report_style,
            request.enable_deep_thinking,
            request.enable_clarification,
            request.max_clarification_rounds,
            user_id,  # Add user_id to workflow
        ),
        media_type="text/event-stream",
    )


def _process_tool_call_chunks(tool_call_chunks):
    """Process tool call chunks and sanitize arguments."""
    chunks = []
    for chunk in tool_call_chunks:
        chunks.append(
            {
                "name": chunk.get("name", ""),
                "args": sanitize_args(chunk.get("args", "")),
                "id": chunk.get("id", ""),
                "index": chunk.get("index", 0),
                "type": chunk.get("type", ""),
            }
        )
    return chunks


def _get_agent_name(agent, message_metadata):
    """Extract agent name from agent tuple."""
    agent_name = "unknown"
    if agent and len(agent) > 0:
        agent_name = agent[0].split(":")[0] if ":" in agent[0] else agent[0]
    else:
        agent_name = message_metadata.get("langgraph_node", "unknown")
    return agent_name


def _create_event_stream_message(
    message_chunk, message_metadata, thread_id, agent_name
):
    """Create base event stream message."""
    content = message_chunk.content
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    
    event_stream_message = {
        "thread_id": thread_id,
        "agent": agent_name,
        "id": message_chunk.id,
        "role": "assistant",
        "checkpoint_ns": message_metadata.get("checkpoint_ns", ""),
        "langgraph_node": message_metadata.get("langgraph_node", ""),
        "langgraph_path": message_metadata.get("langgraph_path", ""),
        "langgraph_step": message_metadata.get("langgraph_step", ""),
        "content": content,
    }

    # Add optional fields
    if message_chunk.additional_kwargs.get("reasoning_content"):
        event_stream_message["reasoning_content"] = message_chunk.additional_kwargs[
            "reasoning_content"
        ]

    if message_chunk.response_metadata.get("finish_reason"):
        event_stream_message["finish_reason"] = message_chunk.response_metadata.get(
            "finish_reason"
        )

    return event_stream_message


def _create_interrupt_event(thread_id, event_data):
    """Create interrupt event."""
    return _make_event(
        "interrupt",
        {
            "thread_id": thread_id,
            "id": event_data["__interrupt__"][0].ns[0],
            "role": "assistant",
            "content": event_data["__interrupt__"][0].value,
            "finish_reason": "interrupt",
            "options": [
                {"text": "Edit plan", "value": "edit_plan"},
                {"text": "Start research", "value": "accepted"},
            ],
        },
    )


def _process_initial_messages(message, thread_id):
    """Process initial messages and yield formatted events."""
    json_data = json.dumps(
        {
            "thread_id": thread_id,
            "id": "run--" + message.get("id", uuid4().hex),
            "role": "user",
            "content": message.get("content", ""),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    chat_stream_message(
        thread_id, f"event: message_chunk\ndata: {json_data}\n\n", "none"
    )


async def _process_message_chunk(message_chunk, message_metadata, thread_id, agent):
    """Process a single message chunk and yield appropriate events."""
    agent_name = _get_agent_name(agent, message_metadata)
    event_stream_message = _create_event_stream_message(
        message_chunk, message_metadata, thread_id, agent_name
    )

    if isinstance(message_chunk, ToolMessage):
        # Tool Message - Return the result of the tool call
        event_stream_message["tool_call_id"] = message_chunk.tool_call_id
        yield _make_event("tool_call_result", event_stream_message)
    elif isinstance(message_chunk, AIMessageChunk):
        # AI Message - Raw message tokens
        if message_chunk.tool_calls:
            # AI Message - Tool Call
            event_stream_message["tool_calls"] = message_chunk.tool_calls
            event_stream_message["tool_call_chunks"] = _process_tool_call_chunks(
                message_chunk.tool_call_chunks
            )
            yield _make_event("tool_calls", event_stream_message)
        elif message_chunk.tool_call_chunks:
            # AI Message - Tool Call Chunks
            event_stream_message["tool_call_chunks"] = _process_tool_call_chunks(
                message_chunk.tool_call_chunks
            )
            yield _make_event("tool_call_chunks", event_stream_message)
        else:
            # AI Message - Raw message tokens
            yield _make_event("message_chunk", event_stream_message)


async def _stream_graph_events(
    graph_instance, workflow_input, workflow_config, thread_id
):
    """Stream events from the graph and process them."""
    try:
        async for agent, _, event_data in graph_instance.astream(
            workflow_input,
            config=workflow_config,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            if isinstance(event_data, dict):
                if "__interrupt__" in event_data:
                    yield _create_interrupt_event(thread_id, event_data)
                continue

            message_chunk, message_metadata = cast(
                tuple[BaseMessage, dict[str, Any]], event_data
            )

            async for event in _process_message_chunk(
                message_chunk, message_metadata, thread_id, agent
            ):
                yield event
    except psycopg.OperationalError as e:
        # Database connection errors - log with more details
        logger.error(
            f"Database connection error during graph execution for thread {thread_id}: {e}",
            exc_info=True
        )
        yield _make_event(
            "error",
            {
                "thread_id": thread_id,
                "error": "Database connection error. The research may be incomplete but will continue.",
                "error_type": "database_connection",
            },
        )
    except psycopg.InterfaceError as e:
        # Database interface errors
        logger.error(
            f"Database interface error during graph execution for thread {thread_id}: {e}",
            exc_info=True
        )
        yield _make_event(
            "error",
            {
                "thread_id": thread_id,
                "error": "Database interface error. The research may be incomplete but will continue.",
                "error_type": "database_interface",
            },
        )
    except Exception as e:
        # General errors
        logger.exception(f"Unexpected error during graph execution for thread {thread_id}")
        yield _make_event(
            "error",
            {
                "thread_id": thread_id,
                "error": "Error during graph execution",
                "error_type": "general",
            },
        )


async def _astream_workflow_generator(
    messages: List[dict],
    thread_id: str,
    resources: List[Resource],
    max_plan_iterations: int,
    max_step_num: int,
    max_search_results: int,
    auto_accepted_plan: bool,
    interrupt_feedback: str,
    mcp_settings: dict,
    enable_background_investigation: bool,
    report_style: ReportStyle,
    enable_deep_thinking: bool,
    enable_clarification: bool,
    max_clarification_rounds: int,
    user_id: str | None = None,
):
    # Process initial messages
    for message in messages:
        if isinstance(message, dict) and "content" in message:
            _process_initial_messages(message, thread_id)

    # Prepare workflow input
    workflow_input = {
        "messages": messages,
        "plan_iterations": 0,
        "final_report": "",
        "current_plan": None,
        "observations": [],
        "auto_accepted_plan": auto_accepted_plan,
        "enable_background_investigation": enable_background_investigation,
        "research_topic": messages[-1]["content"] if messages else "",
        "enable_clarification": enable_clarification,
        "max_clarification_rounds": max_clarification_rounds,
    }

    if not auto_accepted_plan and interrupt_feedback:
        resume_msg = f"[{interrupt_feedback}]"
        if messages:
            resume_msg += f" {messages[-1]['content']}"
        workflow_input = Command(resume=resume_msg)

    # Prepare workflow config
    workflow_config = {
        "thread_id": thread_id,
        "user_id": user_id,  # Add user_id for multi-user support
        "resources": resources,
        "max_plan_iterations": max_plan_iterations,
        "max_step_num": max_step_num,
        "max_search_results": max_search_results,
        "mcp_settings": mcp_settings,
        "report_style": report_style.value,
        "enable_deep_thinking": enable_deep_thinking,
        "recursion_limit": get_recursion_limit(),
    }

    checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
    checkpoint_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "")
    # Handle checkpointer if configured
    connection_kwargs = {
        "autocommit": True,
        "row_factory": "dict_row",
        "prepare_threshold": 0,
    }
    if checkpoint_saver and checkpoint_url != "":
        if checkpoint_url.startswith("postgresql://"):
            logger.info("start async postgres checkpointer.")
            
            # Get connection stability parameters from environment
            from src.config.loader import get_int_env
            connect_timeout = get_int_env("DB_CONNECT_TIMEOUT", 60)
            keepalives_idle = get_int_env("DB_KEEPALIVES_IDLE", 30)
            keepalives_interval = get_int_env("DB_KEEPALIVES_INTERVAL", 10)
            keepalives_count = get_int_env("DB_KEEPALIVES_COUNT", 5)
            
            # Build connection URL with enhanced stability parameters
            checkpoint_url_enhanced = checkpoint_url
            
            # Add SSL mode if not present (required for Railway)
            if "sslmode" not in checkpoint_url_enhanced:
                separator = "&" if "?" in checkpoint_url_enhanced else "?"
                checkpoint_url_enhanced = f"{checkpoint_url_enhanced}{separator}sslmode=require"
                logger.info("Added sslmode=require to PostgreSQL connection URL")
            else:
                separator = "&"
            
            # Add keepalive and timeout parameters
            checkpoint_url_enhanced += (
                f"{separator}"
                f"keepalives=1&"
                f"keepalives_idle={keepalives_idle}&"
                f"keepalives_interval={keepalives_interval}&"
                f"keepalives_count={keepalives_count}&"
                f"connect_timeout={connect_timeout}"
            )
            
            logger.info(
                f"PostgreSQL connection configured with: "
                f"keepalives_idle={keepalives_idle}s, "
                f"keepalives_interval={keepalives_interval}s, "
                f"keepalives_count={keepalives_count}, "
                f"connect_timeout={connect_timeout}s"
            )
            
            # Create connection pool with enhanced stability settings
            async with AsyncConnectionPool(
                checkpoint_url_enhanced,
                kwargs=connection_kwargs,
                min_size=1,           # Minimum connections in pool
                max_size=10,          # Maximum connections in pool
                timeout=30,           # Timeout for acquiring connection from pool
                max_lifetime=3600,    # Maximum connection lifetime (1 hour)
                max_idle=600,         # Maximum idle time before reconnection (10 minutes)
                reconnect_timeout=10, # Reconnection timeout
                check=AsyncConnectionPool.check_connection  # Connection health check
            ) as conn:
                checkpointer = AsyncPostgresSaver(conn)
                await checkpointer.setup()
                graph.checkpointer = checkpointer
                graph.store = in_memory_store
                logger.info("AsyncPostgresSaver initialized with enhanced connection pool")
                async for event in _stream_graph_events(
                    graph, workflow_input, workflow_config, thread_id
                ):
                    yield event

        if checkpoint_url.startswith("mongodb://"):
            logger.info("start async mongodb checkpointer.")
            async with AsyncMongoDBSaver.from_conn_string(
                checkpoint_url
            ) as checkpointer:
                graph.checkpointer = checkpointer
                graph.store = in_memory_store
                async for event in _stream_graph_events(
                    graph, workflow_input, workflow_config, thread_id
                ):
                    yield event
    else:
        # Use graph without MongoDB checkpointer
        async for event in _stream_graph_events(
            graph, workflow_input, workflow_config, thread_id
        ):
            yield event


def _make_event(event_type: str, data: dict[str, any]):
    if data.get("content") == "":
        data.pop("content")
    # Ensure JSON serialization with proper encoding
    try:
        json_data = json.dumps(data, ensure_ascii=False)

        finish_reason = data.get("finish_reason", "")
        chat_stream_message(
            data.get("thread_id", ""),
            f"event: {event_type}\ndata: {json_data}\n\n",
            finish_reason,
        )

        return f"event: {event_type}\ndata: {json_data}\n\n"
    except (TypeError, ValueError) as e:
        logger.error(f"Error serializing event data: {e}")
        # Return a safe error event
        error_data = json.dumps({"error": "Serialization failed"}, ensure_ascii=False)
        return f"event: error\ndata: {error_data}\n\n"


@app.post("/api/tts")
async def text_to_speech(request: TTSRequest):
    """Convert text to speech using volcengine TTS API."""
    app_id = get_str_env("VOLCENGINE_TTS_APPID", "")
    if not app_id:
        raise HTTPException(status_code=400, detail="VOLCENGINE_TTS_APPID is not set")
    access_token = get_str_env("VOLCENGINE_TTS_ACCESS_TOKEN", "")
    if not access_token:
        raise HTTPException(
            status_code=400, detail="VOLCENGINE_TTS_ACCESS_TOKEN is not set"
        )

    try:
        cluster = get_str_env("VOLCENGINE_TTS_CLUSTER", "volcano_tts")
        voice_type = get_str_env("VOLCENGINE_TTS_VOICE_TYPE", "BV700_V2_streaming")

        tts_client = VolcengineTTS(
            appid=app_id,
            access_token=access_token,
            cluster=cluster,
            voice_type=voice_type,
        )
        # Call the TTS API
        result = tts_client.text_to_speech(
            text=request.text[:1024],
            encoding=request.encoding,
            speed_ratio=request.speed_ratio,
            volume_ratio=request.volume_ratio,
            pitch_ratio=request.pitch_ratio,
            text_type=request.text_type,
            with_frontend=request.with_frontend,
            frontend_type=request.frontend_type,
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=str(result["error"]))

        # Decode the base64 audio data
        audio_data = base64.b64decode(result["audio_data"])

        # Return the audio file
        return Response(
            content=audio_data,
            media_type=f"audio/{request.encoding}",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=tts_output.{request.encoding}"
                )
            },
        )

    except Exception as e:
        logger.exception(f"Error in TTS endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/podcast/generate")
async def generate_podcast(request: GeneratePodcastRequest):
    try:
        report_content = request.content
        print(report_content)
        workflow = build_podcast_graph()
        final_state = workflow.invoke({"input": report_content})
        audio_bytes = final_state["output"]
        return Response(content=audio_bytes, media_type="audio/mp3")
    except Exception as e:
        logger.exception(f"Error occurred during podcast generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/ppt/generate")
async def generate_ppt(request: GeneratePPTRequest):
    try:
        report_content = request.content
        print(report_content)
        workflow = build_ppt_graph()
        final_state = workflow.invoke({"input": report_content})
        generated_file_path = final_state["generated_file_path"]
        with open(generated_file_path, "rb") as f:
            ppt_bytes = f.read()
        return Response(
            content=ppt_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    except Exception as e:
        logger.exception(f"Error occurred during ppt generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/prose/generate")
async def generate_prose(request: GenerateProseRequest):
    try:
        sanitized_prompt = request.prompt.replace("\r\n", "").replace("\n", "")
        logger.info(f"Generating prose for prompt: {sanitized_prompt}")
        workflow = build_prose_graph()
        events = workflow.astream(
            {
                "content": request.prompt,
                "option": request.option,
                "command": request.command,
            },
            stream_mode="messages",
            subgraphs=True,
        )
        return StreamingResponse(
            (f"data: {event[0].content}\n\n" async for _, event in events),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.exception(f"Error occurred during prose generation: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/prompt/enhance")
async def enhance_prompt(request: EnhancePromptRequest):
    try:
        sanitized_prompt = request.prompt.replace("\r\n", "").replace("\n", "")
        logger.info(f"Enhancing prompt: {sanitized_prompt}")

        # Convert string report_style to ReportStyle enum
        report_style = None
        if request.report_style:
            try:
                # Handle both uppercase and lowercase input
                style_mapping = {
                    "ACADEMIC": ReportStyle.ACADEMIC,
                    "POPULAR_SCIENCE": ReportStyle.POPULAR_SCIENCE,
                    "NEWS": ReportStyle.NEWS,
                    "SOCIAL_MEDIA": ReportStyle.SOCIAL_MEDIA,
                    "STRATEGIC_INVESTMENT": ReportStyle.STRATEGIC_INVESTMENT,
                }
                report_style = style_mapping.get(
                    request.report_style.upper(), ReportStyle.ACADEMIC
                )
            except Exception:
                # If invalid style, default to ACADEMIC
                report_style = ReportStyle.ACADEMIC
        else:
            report_style = ReportStyle.ACADEMIC

        workflow = build_prompt_enhancer_graph()
        final_state = workflow.invoke(
            {
                "prompt": request.prompt,
                "context": request.context,
                "report_style": report_style,
            }
        )
        return {"result": final_state["output"]}
    except Exception as e:
        logger.exception(f"Error occurred during prompt enhancement: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.post("/api/mcp/server/metadata", response_model=MCPServerMetadataResponse)
async def mcp_server_metadata(request: MCPServerMetadataRequest):
    """Get information about an MCP server."""
    # Check if MCP server configuration is enabled
    if not get_bool_env("ENABLE_MCP_SERVER_CONFIGURATION", False):
        raise HTTPException(
            status_code=403,
            detail="MCP server configuration is disabled. Set ENABLE_MCP_SERVER_CONFIGURATION=true to enable MCP features.",
        )

    try:
        # Set default timeout with a longer value for this endpoint
        timeout = 300  # Default to 300 seconds for this endpoint

        # Use custom timeout from request if provided
        if request.timeout_seconds is not None:
            timeout = request.timeout_seconds

        # Load tools from the MCP server using the utility function
        tools = await load_mcp_tools(
            server_type=request.transport,
            command=request.command,
            args=request.args,
            url=request.url,
            env=request.env,
            headers=request.headers,
            timeout_seconds=timeout,
        )

        # Create the response with tools
        response = MCPServerMetadataResponse(
            transport=request.transport,
            command=request.command,
            args=request.args,
            url=request.url,
            env=request.env,
            headers=request.headers,
            tools=tools,
        )

        return response
    except Exception as e:
        logger.exception(f"Error in MCP server metadata endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.get("/api/rag/config", response_model=RAGConfigResponse)
async def rag_config():
    """Get the config of the RAG."""
    return RAGConfigResponse(provider=SELECTED_RAG_PROVIDER)


@app.get("/api/rag/resources", response_model=RAGResourcesResponse)
async def rag_resources(request: Annotated[RAGResourceRequest, Query()]):
    """Get the resources of the RAG."""
    retriever = build_retriever()
    if retriever:
        return RAGResourcesResponse(resources=retriever.list_resources(request.query))
    return RAGResourcesResponse(resources=[])


@app.get("/api/config", response_model=ConfigResponse)
async def config():
    """Get the config of the server."""
    return ConfigResponse(
        rag=RAGConfigResponse(provider=SELECTED_RAG_PROVIDER),
        models=get_configured_llm_models(),
    )


# ============================================================
# Authentication APIs
# ============================================================

@app.post("/api/auth/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """User registration endpoint."""
    try:
        db_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL")
        
        # Add SSL mode to connection URL if not already present (required for Railway)
        if "sslmode" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url = f"{db_url}{separator}sslmode=require"
        
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                # Check if username or email already exists
                cur.execute(
                    "SELECT id FROM users WHERE username = %s OR email = %s",
                    (request.username, request.email),
                )
                if cur.fetchone():
                    raise HTTPException(
                        status_code=400,
                        detail="Username or email already exists"
                    )
                
                # Create user
                password_hash = hash_password(request.password)
                cur.execute(
                    """
                    INSERT INTO users (username, email, password_hash, display_name)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, username, display_name
                    """,
                    (request.username, request.email, password_hash, request.display_name),
                )
                
                user = cur.fetchone()
                conn.commit()
                
                # Generate JWT token
                token = create_access_token(str(user[0]), user[1])
                
                return AuthResponse(
                    access_token=token,
                    user_id=str(user[0]),
                    username=user[1],
                    display_name=user[2],
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Registration error: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed")


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """User login endpoint."""
    try:
        db_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL")
        
        # Add SSL mode to connection URL if not already present (required for Railway)
        if "sslmode" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url = f"{db_url}{separator}sslmode=require"
        
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                # Query user (support username or email login)
                cur.execute(
                    """
                    SELECT id, username, password_hash, display_name, is_active
                    FROM users
                    WHERE username = %s OR email = %s
                    """,
                    (request.username, request.username),
                )
                
                user = cur.fetchone()
                
                if not user:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid credentials"
                    )
                
                user_id, username, password_hash, display_name, is_active = user
                
                # Check account status
                if not is_active:
                    raise HTTPException(
                        status_code=403,
                        detail="Account disabled"
                    )
                
                # Verify password
                if not verify_password(request.password, password_hash):
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid credentials"
                    )
                
                # Generate JWT token
                token = create_access_token(str(user_id), username)
                
                return AuthResponse(
                    access_token=token,
                    user_id=str(user_id),
                    username=username,
                    display_name=display_name,
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")


@app.get("/api/auth/me", response_model=UserInfo)
async def get_user_info(user_id: str = Depends(get_current_user)):
    """Get current user information."""
    try:
        db_url = get_str_env("LANGGRAPH_CHECKPOINT_DB_URL")
        
        # Add SSL mode to connection URL if not already present (required for Railway)
        if "sslmode" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url = f"{db_url}{separator}sslmode=require"
        
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, username, email, display_name, created_at, 
                           daily_quota, used_today
                    FROM users WHERE id = %s
                    """,
                    (user_id,),
                )
                
                user = cur.fetchone()
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")
                
                return UserInfo(
                    user_id=str(user[0]),
                    username=user[1],
                    email=user[2],
                    display_name=user[3],
                    created_at=str(user[4]),
                    daily_quota=user[5],
                    used_today=user[6],
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Get user info error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get user info")


# ============================================================
# Research History APIs
# ============================================================

@app.get("/api/researches")
async def get_researches(
    limit: int = 20,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
):
    """Get user's completed research list."""
    try:
        researches = get_user_researches(user_id, limit, offset)
        return {"data": researches}
    except Exception as e:
        logger.exception(f"Error getting researches: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.get("/api/research/{thread_id}")
async def get_research(
    thread_id: str,
    user_id: str = Depends(get_current_user),
):
    """Get complete research data (observations + plan + report) for viewing."""
    try:
        research = get_research_report(thread_id, user_id)
        if not research:
            raise HTTPException(
                status_code=404,
                detail="Research not found or access denied"
            )
        return research
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting research: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


@app.delete("/api/research/{thread_id}")
async def delete_research_endpoint(
    thread_id: str,
    user_id: str = Depends(get_current_user),
):
    """Delete a research (with ownership verification)."""
    try:
        deleted = delete_research(thread_id, user_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Research not found or access denied"
            )
        return {"message": "Research deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting research: {str(e)}")
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)

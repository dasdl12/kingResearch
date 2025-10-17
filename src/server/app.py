# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import base64
import json
import logging
from typing import Annotated, Any, List, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langgraph.checkpoint.mongodb import AsyncMongoDBSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool

from src.config.configuration import get_recursion_limit
from src.config.loader import get_bool_env, get_str_env
from src.config.report_style import ReportStyle
from src.config.tools import SELECTED_RAG_PROVIDER
from src.graph.builder import build_graph_with_memory
from src.graph.checkpoint import chat_stream_message
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
from src.server.rag_request import (
    RAGConfigResponse,
    RAGResourceRequest,
    RAGResourcesResponse,
)
from src.server.conversation_request import (
    CreateConversationRequest,
    UpdateConversationRequest,
    ConversationResponse,
    ConversationListResponse,
    MessageResponse,
    MessageListResponse,
    GenerateTitleRequest,
    GenerateTitleResponse,
    ExportConversationResponse,
)
from src.database.models import (
    ConversationRepository,
    MessageRepository,
    Message as DBMessage,
    init_database,
)
from src.tools import VolcengineTTS
from src.utils.json_utils import sanitize_args

logger = logging.getLogger(__name__)

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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Add PUT and DELETE
    allow_headers=["*"],  # Now allow all headers, but can be restricted further
)

# Load examples into Milvus if configured
load_examples()

# Initialize database tables
init_database()

in_memory_store = InMemoryStore()
graph = build_graph_with_memory()


async def _auto_generate_title(conversation_id: str, first_message: str):
    """Auto-generate title for conversation based on first message."""
    try:
        from src.llms.llm import get_llm_by_type
        
        llm = get_llm_by_type("basic")
        prompt = f"""Based on this user question, generate a short, descriptive title (max 6 words):

Question: {first_message}

Generate ONLY the title, no quotes or extra text."""

        response = llm.invoke(prompt)
        title = response.content.strip().strip('"').strip("'")
        
        # Fallback to first 50 chars if generation fails
        if not title or len(title) > 100:
            title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        
        # Update conversation title
        conv_repo = ConversationRepository()
        try:
            conv_repo.update_conversation(conversation_id, title=title)
            logger.info(f"Auto-generated title for conversation {conversation_id}: {title}")
        finally:
            conv_repo.close()
            
    except Exception as e:
        logger.error(f"Failed to auto-generate title: {e}")


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    # Check if MCP server configuration is enabled
    mcp_enabled = get_bool_env("ENABLE_MCP_SERVER_CONFIGURATION", False)

    # Validate MCP settings if provided
    if request.mcp_settings and not mcp_enabled:
        raise HTTPException(
            status_code=403,
            detail="MCP server configuration is disabled. Set ENABLE_MCP_SERVER_CONFIGURATION=true to enable MCP features.",
        )

    thread_id = request.thread_id
    conversation_id = thread_id  # Use thread_id as conversation_id
    
    # Check if we need to create a new conversation
    need_create = False
    if thread_id == "__default__":
        need_create = True
    else:
        # Verify the conversation exists (防止使用已删除的ID)
        conv_repo = ConversationRepository()
        try:
            existing_conv = conv_repo.get_conversation(thread_id)
            if not existing_conv:
                logger.warning(f"⚠️ Thread ID {thread_id} references non-existent conversation, creating new one")
                need_create = True
        finally:
            conv_repo.close()
    
    if need_create:
        # Create a new conversation
        conv_repo = ConversationRepository()
        try:
            conversation = conv_repo.create_conversation(title="New Conversation")
            if conversation:
                conversation_id = conversation.id
                thread_id = conversation.id
                logger.info(f"✅ Created new conversation: {conversation_id}")
            else:
                thread_id = str(uuid4())
                conversation_id = thread_id
        finally:
            conv_repo.close()
    
    # Save user message to database
    if request.messages and len(request.messages) > 0:
        msg_repo = MessageRepository()
        try:
            user_message = request.messages[-1]  # Get last user message
            if isinstance(user_message, dict) and user_message.get("role") == "user":
                db_message = DBMessage(
                    conversation_id=conversation_id,
                    role="user",
                    content=user_message.get("content", ""),
                    metadata={"resources": [r.dict() for r in request.resources] if request.resources else None}
                )
                msg_repo.add_message(db_message)
                logger.info(f"💬 User message saved to conversation {conversation_id}")
                
                # 不再使用auto_generate_title，标题由planner生成
        finally:
            msg_repo.close()

    return StreamingResponse(
        _astream_workflow_generator(
            request.model_dump()["messages"],
            thread_id,
            conversation_id,
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
    event_stream_message = {
        "thread_id": thread_id,
        "agent": agent_name,
        "id": message_chunk.id,
        "role": "assistant",
        "checkpoint_ns": message_metadata.get("checkpoint_ns", ""),
        "langgraph_node": message_metadata.get("langgraph_node", ""),
        "langgraph_path": message_metadata.get("langgraph_path", ""),
        "langgraph_step": message_metadata.get("langgraph_step", ""),
        "content": message_chunk.content,
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


async def _process_message_chunk(message_chunk, message_metadata, thread_id, agent, conversation_id=None):
    """Process a single message chunk and yield appropriate events."""
    agent_name = _get_agent_name(agent, message_metadata)
    event_stream_message = _create_event_stream_message(
        message_chunk, message_metadata, thread_id, agent_name
    )

    # 检查是否包含conversation_title更新（从planner的additional_kwargs）
    if hasattr(message_chunk, 'additional_kwargs') and message_chunk.additional_kwargs.get("conversation_title"):
        title = message_chunk.additional_kwargs["conversation_title"]
        logger.info(f"🟡 Sending conversation_title_updated event: '{title}'")
        yield _make_event("conversation_title_updated", {
            "thread_id": thread_id,
            "conversation_id": conversation_id or thread_id,
            "id": "title_update_from_planner",
            "role": "system",
            "title": title
        })
    
    # 方案C：保存关键节点的AI消息到messages表
    # 保存planner和reporter的完整消息（不保存中间的tool calls）
    if isinstance(message_chunk, AIMessageChunk):
        finish_reason = message_chunk.response_metadata.get("finish_reason") if hasattr(message_chunk, 'response_metadata') else None
        if finish_reason == "stop" and message_chunk.content and conversation_id:
            # 只保存来自planner、reporter、coordinator的完整消息
            if agent_name in ["planner", "reporter", "coordinator"]:
                msg_repo = MessageRepository()
                try:
                    # 检查是否已存在（避免重复保存）
                    existing_messages = msg_repo.get_messages(conversation_id, limit=1000)
                    if not any(msg.id == str(message_chunk.id) for msg in existing_messages):
                        db_message = DBMessage(
                            id=str(message_chunk.id),
                            conversation_id=conversation_id,
                            role="assistant",
                            content=message_chunk.content,
                            agent=agent_name,
                            metadata=message_chunk.additional_kwargs if hasattr(message_chunk, 'additional_kwargs') else None
                        )
                        msg_repo.add_message(db_message)
                        logger.info(f"💾 Saved {agent_name} message to conversation {conversation_id}")
                except Exception as e:
                    logger.error(f"Failed to save AI message: {e}")
                finally:
                    msg_repo.close()

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
    graph_instance, workflow_input, workflow_config, thread_id, conversation_id=None
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
                message_chunk, message_metadata, thread_id, agent, conversation_id
            ):
                yield event
    except Exception as e:
        logger.exception("Error during graph execution")
        yield _make_event(
            "error",
            {
                "thread_id": thread_id,
                "error": "Error during graph execution",
            },
        )


async def _astream_workflow_generator(
    messages: List[dict],
    thread_id: str,
    conversation_id: str,
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
):
    # Send initial event with full conversation data
    conv_repo = ConversationRepository()
    try:
        conversation = conv_repo.get_conversation(conversation_id)
        conv_data = {
            "thread_id": thread_id,
            "conversation_id": conversation_id,
            "id": "init",
            "role": "system"
        }
        if conversation:
            conv_data["conversation"] = {
                "id": conversation.id,
                "title": conversation.title,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat(),
                "message_count": conversation.message_count,
                "metadata": conversation.metadata
            }
            logger.info(f"🔵 Sending conversation_init with data: {conversation.id}, title: {conversation.title}")
        else:
            logger.warning(f"⚠️ Conversation {conversation_id} not found when sending conversation_init")
        yield _make_event("conversation_init", conv_data)
    finally:
        conv_repo.close()
    
    # Track accumulated AI response for database saving
    accumulated_response = {"content": "", "agent": None, "finish_reason": None}
    
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
        "conversation_id": conversation_id,  # 添加conversation_id到state
    }

    if not auto_accepted_plan and interrupt_feedback:
        resume_msg = f"[{interrupt_feedback}]"
        if messages:
            resume_msg += f" {messages[-1]['content']}"
        workflow_input = Command(resume=resume_msg)

    # Prepare workflow config
    workflow_config = {
        "thread_id": thread_id,
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
            async with AsyncConnectionPool(
                checkpoint_url, kwargs=connection_kwargs
            ) as conn:
                checkpointer = AsyncPostgresSaver(conn)
                await checkpointer.setup()
                graph.checkpointer = checkpointer
                graph.store = in_memory_store
                async for event in _stream_graph_events(
                    graph, workflow_input, workflow_config, thread_id, conversation_id
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
                    graph, workflow_input, workflow_config, thread_id, conversation_id
                ):
                    yield event
    else:
        # Use graph without MongoDB checkpointer
        async for event in _stream_graph_events(
            graph, workflow_input, workflow_config, thread_id, conversation_id
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

# ============================================================================
# Conversation Management APIs
# ============================================================================


@app.post("/api/conversations", response_model=ConversationResponse)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    repo = ConversationRepository()
    try:
        conversation = repo.create_conversation(
            title=request.title or "New Conversation",
            metadata=request.metadata
        )
        
        if not conversation:
            raise HTTPException(status_code=500, detail="Failed to create conversation")
        
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            metadata=conversation.metadata
        )
    finally:
        repo.close()


@app.get("/api/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """List all conversations."""
    repo = ConversationRepository()
    try:
        conversations = repo.list_conversations(limit=limit, offset=offset)
        
        return ConversationListResponse(
            conversations=[
                ConversationResponse(
                    id=conv.id,
                    title=conv.title,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    message_count=conv.message_count,
                    metadata=conv.metadata
                )
                for conv in conversations
            ],
            total=len(conversations),
            limit=limit,
            offset=offset
        )
    finally:
        repo.close()


@app.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    """Get a specific conversation."""
    repo = ConversationRepository()
    try:
        conversation = repo.get_conversation(conversation_id)
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            metadata=conversation.metadata
        )
    finally:
        repo.close()


@app.put("/api/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    """Update a conversation's title or metadata."""
    repo = ConversationRepository()
    try:
        success = repo.update_conversation(
            conversation_id=conversation_id,
            title=request.title,
            metadata=request.metadata
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get updated conversation
        conversation = repo.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=conversation.message_count,
            metadata=conversation.metadata
        )
    finally:
        repo.close()


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    repo = ConversationRepository()
    try:
        success = repo.delete_conversation(conversation_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {"status": "success", "message": "Conversation deleted"}
    finally:
        repo.close()


@app.get("/api/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get messages for a conversation."""
    msg_repo = MessageRepository()
    try:
        messages = msg_repo.get_messages(
            conversation_id=conversation_id,
            limit=limit,
            offset=offset
        )
        
        return MessageListResponse(
            messages=[
                MessageResponse(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    role=msg.role,
                    content=msg.content,
                    agent=msg.agent,
                    metadata=msg.metadata,
                    created_at=msg.created_at
                )
                for msg in messages
            ],
            total=len(messages),
            limit=limit,
            offset=offset
        )
    finally:
        msg_repo.close()


@app.post("/api/conversations/generate-title", response_model=GenerateTitleResponse)
async def generate_conversation_title(request: GenerateTitleRequest):
    """Generate a title for a conversation based on the first message."""
    from src.llms.llm import get_llm_by_type
    
    try:
        # Use the basic model to generate a concise title
        llm = get_llm_by_type("basic")
        
        prompt = f"""Based on this user question, generate a short, descriptive title (max 6 words):

Question: {request.first_message}

Generate ONLY the title, no quotes or extra text."""

        response = llm.invoke(prompt)
        title = response.content.strip().strip('"').strip("'")
        
        # Fallback to first 50 chars if generation fails
        if not title or len(title) > 100:
            title = request.first_message[:50] + ("..." if len(request.first_message) > 50 else "")
        
        return GenerateTitleResponse(title=title)
        
    except Exception as e:
        logger.error(f"Failed to generate title: {e}")
        # Fallback to first message preview
        title = request.first_message[:50] + ("..." if len(request.first_message) > 50 else "")
        return GenerateTitleResponse(title=title)


@app.get("/api/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = Query("markdown", regex="^(markdown|json)$")
):
    """Export a conversation in markdown or JSON format."""
    conv_repo = ConversationRepository()
    msg_repo = MessageRepository()
    
    try:
        # Get conversation
        conversation = conv_repo.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get all messages
        messages = msg_repo.get_messages(conversation_id, limit=1000)
        
        if format == "markdown":
            # Generate markdown export
            lines = [
                f"# {conversation.title}",
                "",
                f"**Created:** {conversation.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                f"**Updated:** {conversation.updated_at.strftime('%Y-%m-%d %H:%M:%S')}",
                f"**Messages:** {conversation.message_count}",
                "",
                "---",
                ""
            ]
            
            for msg in messages:
                role_label = {
                    "user": "👤 User",
                    "assistant": "🤖 Assistant",
                    "system": "⚙️ System"
                }.get(msg.role, msg.role.capitalize())
                
                if msg.agent:
                    role_label += f" ({msg.agent})"
                
                lines.append(f"## {role_label}")
                lines.append(f"*{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}*")
                lines.append("")
                lines.append(msg.content)
                lines.append("")
                lines.append("---")
                lines.append("")
            
            content = "\n".join(lines)
            
            return Response(
                content=content,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="conversation_{conversation_id}.md"'
                }
            )
        else:
            # JSON export
            export_data = {
                "conversation": {
                    "id": conversation.id,
                    "title": conversation.title,
                    "created_at": conversation.created_at.isoformat(),
                    "updated_at": conversation.updated_at.isoformat(),
                    "message_count": conversation.message_count,
                    "metadata": conversation.metadata
                },
                "messages": [
                    {
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "agent": msg.agent,
                        "metadata": msg.metadata,
                        "created_at": msg.created_at.isoformat()
                    }
                    for msg in messages
                ]
            }
            
            return Response(
                content=json.dumps(export_data, indent=2, ensure_ascii=False),
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="conversation_{conversation_id}.json"'
                }
            )
            
    finally:
        conv_repo.close()
        msg_repo.close()


import json
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from langchain_core.messages import AIMessageChunk, HumanMessage
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import create_agent_graph
from app.api.v1.schemas import ChatRequest, ChatResponse, HealthResponse
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()

# Shared compiled graph instance with in-memory checkpointer
agent_graph = create_agent_graph()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request_body: ChatRequest, req: Request):
    request_id = getattr(req.state, "request_id", "unknown")
    handler = CallbackHandler()
    config = {
        "configurable": {"thread_id": request_body.thread_id},
        "callbacks": [handler],
        "metadata": {
            "langfuse_session_id": request_body.thread_id,
            "langfuse_user_id": request_body.user_id,
            "request_id": request_id,
        },
    }

    result = await agent_graph.ainvoke(
        {"messages": [HumanMessage(content=request_body.message)]},
        config=config,
    )
    full_response = str(result["messages"][-1].content)

    # Flush traces to Langfuse
    try:
        get_client().flush()
    except Exception:
        pass

    return ChatResponse(
        response=full_response,
        thread_id=request_body.thread_id,
        user_id=request_body.user_id,
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(request_body: ChatRequest, req: Request):
    request_id = getattr(req.state, "request_id", "unknown")
    handler = CallbackHandler()
    config = {
        "configurable": {"thread_id": request_body.thread_id},
        "callbacks": [handler],
        "metadata": {
            "langfuse_session_id": request_body.thread_id,
            "langfuse_user_id": request_body.user_id,
            "request_id": request_id,
        },
    }

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for chunk, metadata in agent_graph.astream(
                {"messages": [HumanMessage(content=request_body.message)]},
                config=config,
                stream_mode="messages",
            ):
                # Check for client disconnect to avoid wasted tokens
                if await req.is_disconnected():
                    break

                # Stream only assistant text tokens
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    yield json.dumps({"token": chunk.content})
            
            # Send completion signal
            yield json.dumps({
                "done": True,
                "thread_id": request_body.thread_id,
                "request_id": request_id,
            })
        finally:
            try:
                get_client().flush()
            except Exception:
                pass

    return EventSourceResponse(event_generator())

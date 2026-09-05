from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="The user query or instruction")
    thread_id: str = Field(
        default="default-session",
        description="Session or conversation thread ID for memory persistence",
    )
    user_id: Optional[str] = Field(
        default="default-user",
        description="User identifier for tracing and analytics",
    )


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    user_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str

"""
Chat router — AI chat endpoint for engineers.
Engineers can ask plain English questions about the network.
"""
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from shared.config import get_settings
from shared.redis_client import get_redis_client
from services.ai_agent.groq_client import GroqLLMClient, GroqClientError
from services.ai_agent.prompts import SYSTEM_PROMPT, build_chat_context
from services.network_simulator.devices import DEVICES

router = APIRouter()

# Lazy singleton Groq client
_groq_client: Optional[GroqLLMClient] = None


def get_groq() -> GroqLLMClient:
    global _groq_client
    if _groq_client is None:
        settings = get_settings()
        if not settings.groq_api_key:
            raise HTTPException(status_code=503, detail="Groq API key not configured")
        _groq_client = GroqLLMClient(api_key=settings.groq_api_key, model=settings.groq_model)
    return _groq_client


class ChatMessage(BaseModel):
    role: str      # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    session_id: Optional[str] = None    # Pass existing session ID to maintain context
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    history: List[ChatMessage]


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    AI chat endpoint — engineers can ask questions in plain English.

    Examples:
    - "What's wrong with R1?"
    - "Which devices are currently down?"
    - "What caused the last critical incident?"
    - "Is the network healthy right now?"

    Maintains conversation context via session_id (stored in Redis).
    """
    redis = get_redis_client()
    groq = get_groq()

    # Create or reuse session
    session_id = request.session_id or str(uuid.uuid4())

    # Load existing chat history from Redis
    existing_history = redis.get_chat_history(session_id)

    # Build network context snapshot for the AI
    device_states = {}
    for device in DEVICES:
        state = redis.get_device_state(device.device_id) or "UNKNOWN"
        device_states[device.device_id] = state

    active_alerts = redis.get_all_active_alerts()
    health_score = redis.get_health_score()

    network_snapshot = {
        "device_states": device_states,
        "active_alerts": active_alerts,
        "health_score": health_score,
    }

    # Build messages list for Groq
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add existing history
    for msg in existing_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current user message with network context
    user_message_with_context = build_chat_context(
        user_question=request.message,
        network_snapshot=network_snapshot,
    )
    messages.append({"role": "user", "content": user_message_with_context})

    # Call Groq (no tools for chat — just conversation)
    try:
        response = groq.chat(
            messages=messages,
            tools=None,
            temperature=0.3,    # Slightly higher for conversational responses
            max_tokens=1024,
        )
        reply = response.choices[0].message.content or "I couldn't generate a response."
    except GroqClientError as e:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {str(e)[:100]}")

    # Save messages to Redis session
    redis.add_chat_message(session_id, {"role": "user", "content": request.message})
    redis.add_chat_message(session_id, {"role": "assistant", "content": reply})

    # Return updated history
    updated_history = redis.get_chat_history(session_id)

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        history=[ChatMessage(role=m["role"], content=m["content"]) for m in updated_history],
    )


@router.delete("/chat/{session_id}")
async def clear_chat(session_id: str):
    """Clear chat session history."""
    redis = get_redis_client()
    from shared.redis_client import CHAT_SESSION_KEY
    redis._client.delete(CHAT_SESSION_KEY.format(session_id=session_id))
    return {"message": f"Session {session_id} cleared"}

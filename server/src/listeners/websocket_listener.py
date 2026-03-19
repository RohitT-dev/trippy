"""WebSocket event listener for real-time CrewAI event streaming.

Instantiated at module level so it auto-registers with the CrewAI singleton
event bus the moment this module is imported. The FastAPI app must call
``set_main_loop(asyncio.get_running_loop())`` from its lifespan handler so
that events emitted from background threads (where flow.kickoff() runs) can
safely schedule coroutines back onto the main event loop.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from crewai.events import (
    BaseEventListener,
    CrewKickoffStartedEvent,
    CrewKickoffCompletedEvent,
    CrewKickoffFailedEvent,
    AgentReasoningStartedEvent,
    AgentReasoningCompletedEvent,
    TaskStartedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    LLMCallStartedEvent,
    LLMCallCompletedEvent,
    LLMCallFailedEvent,
    LLMStreamChunkEvent,
    ToolUsageStartedEvent,
    ToolUsageFinishedEvent,
    ToolUsageErrorEvent,
    FlowStartedEvent,
    FlowFinishedEvent,
    MethodExecutionStartedEvent,
    MethodExecutionFinishedEvent,
    MethodExecutionFailedEvent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state – mutated by FastAPI endpoints
# ---------------------------------------------------------------------------

#: All currently connected /ws/events WebSocket clients.
connected_clients: list = []

#: Reference to the uvicorn event loop, set during FastAPI lifespan startup.
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store a reference to the running asyncio loop (called from lifespan)."""
    global _main_loop
    _main_loop = loop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(event) -> str:
    """Return event timestamp as an ISO string."""
    ts = getattr(event, "timestamp", None)
    if isinstance(ts, datetime):
        return ts.isoformat()
    return datetime.utcnow().isoformat()


async def _send_all(message: str) -> None:
    """Send *message* to every connected client, silently pruning dead sockets."""
    dead = []
    for ws in list(connected_clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            connected_clients.remove(ws)
        except ValueError:
            pass


def broadcast(data: dict) -> None:
    """Thread-safe broadcast: schedule *data* to be sent to all WS clients.

    May be called from any thread (including CrewAI's sync worker threads).
    Uses ``run_coroutine_threadsafe`` when a main loop reference is available,
    falling back to ``asyncio.create_task`` when already on the event loop.
    """
    if not connected_clients:
        return
    try:
        message = json.dumps(data, default=str)
    except Exception as exc:
        logger.warning("Failed to serialize event payload: %s", exc)
        return

    loop = _main_loop
    if loop is None:
        # We have no stored loop — try to get the running one (works if we're
        # already on the event loop thread, e.g. during tests).
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("broadcast() called with no event loop available; dropping event")
            return

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is loop:
        # Already on the event loop – schedule as a Task directly.
        asyncio.create_task(_send_all(message))
    else:
        # Called from a worker thread – schedule thread-safely.
        asyncio.run_coroutine_threadsafe(_send_all(message), loop)


# ---------------------------------------------------------------------------
# Listener class
# ---------------------------------------------------------------------------

class WebSocketEventListener(BaseEventListener):
    """Bridges CrewAI's event bus to connected WebSocket clients."""

    def setup_listeners(self, crewai_event_bus):  # noqa: D401

        # ── Crew ──────────────────────────────────────────────────────────────

        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_crew_started(source, event):
            broadcast({
                "type": "crew_kickoff_started",
                "crew": getattr(event, "crew_name", None),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def on_crew_completed(source, event):
            output = getattr(event, "output", None)
            broadcast({
                "type": "crew_kickoff_completed",
                "crew": getattr(event, "crew_name", None),
                "output": str(output)[:300] if output else None,
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(CrewKickoffFailedEvent)
        def on_crew_failed(source, event):
            broadcast({
                "type": "crew_kickoff_failed",
                "crew": getattr(event, "crew_name", None),
                "error": str(getattr(event, "error", "")),
                "timestamp": _ts(event),
            })

        # ── Agent reasoning ───────────────────────────────────────────────────

        @crewai_event_bus.on(AgentReasoningStartedEvent)
        def on_agent_started(source, event):
            broadcast({
                "type": "agent_execution_started",
                "agent": getattr(event, "agent_role", None),
                "task": getattr(event, "task_name", None),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(AgentReasoningCompletedEvent)
        def on_agent_completed(source, event):
            broadcast({
                "type": "agent_execution_completed",
                "agent": getattr(event, "agent_role", None),
                "task": getattr(event, "task_name", None),
                "output": str(getattr(event, "plan", ""))[:300] or None,
                "timestamp": _ts(event),
            })

        # ── Task ──────────────────────────────────────────────────────────────

        @crewai_event_bus.on(TaskStartedEvent)
        def on_task_started(source, event):
            broadcast({
                "type": "task_started",
                "agent": getattr(event, "agent_role", None),
                "task": getattr(event, "task_name", None),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(TaskCompletedEvent)
        def on_task_completed(source, event):
            output = getattr(event, "output", None)
            broadcast({
                "type": "task_completed",
                "agent": getattr(event, "agent_role", None),
                "task": getattr(event, "task_name", None),
                "output": str(output)[:300] if output else None,
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(TaskFailedEvent)
        def on_task_failed(source, event):
            broadcast({
                "type": "task_failed",
                "agent": getattr(event, "agent_role", None),
                "task": getattr(event, "task_name", None),
                "error": str(getattr(event, "error", "")),
                "timestamp": _ts(event),
            })

        # ── LLM ───────────────────────────────────────────────────────────────

        @crewai_event_bus.on(LLMCallStartedEvent)
        def on_llm_started(source, event):
            broadcast({
                "type": "llm_call_started",
                "agent": getattr(event, "agent_role", None),
                "model": getattr(event, "model", None),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(LLMCallCompletedEvent)
        def on_llm_completed(source, event):
            response = getattr(event, "response", None)
            broadcast({
                "type": "llm_call_completed",
                "agent": getattr(event, "agent_role", None),
                "model": getattr(event, "model", None),
                "output": str(response)[:300] if response else None,
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(LLMCallFailedEvent)
        def on_llm_failed(source, event):
            broadcast({
                "type": "llm_call_failed",
                "agent": getattr(event, "agent_role", None),
                "model": getattr(event, "model", None),
                "error": str(getattr(event, "error", "")),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(LLMStreamChunkEvent)
        def on_llm_chunk(source, event):
            chunk = getattr(event, "chunk", None)
            broadcast({
                "type": "llm_stream_chunk",
                "agent": getattr(event, "agent_role", None),
                "chunk": str(chunk) if chunk else None,
                "timestamp": _ts(event),
            })

        # ── Tools ─────────────────────────────────────────────────────────────

        @crewai_event_bus.on(ToolUsageStartedEvent)
        def on_tool_started(source, event):
            broadcast({
                "type": "tool_usage_started",
                "agent": getattr(event, "agent_role", None),
                "tool": getattr(event, "tool_name", None),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def on_tool_finished(source, event):
            output = getattr(event, "output", None)
            broadcast({
                "type": "tool_usage_finished",
                "agent": getattr(event, "agent_role", None),
                "tool": getattr(event, "tool_name", None),
                "output": str(output)[:300] if output else None,
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(ToolUsageErrorEvent)
        def on_tool_error(source, event):
            broadcast({
                "type": "tool_usage_error",
                "agent": getattr(event, "agent_role", None),
                "tool": getattr(event, "tool_name", None),
                "error": str(getattr(event, "error", "")),
                "timestamp": _ts(event),
            })

        # ── Flow ──────────────────────────────────────────────────────────────

        @crewai_event_bus.on(FlowStartedEvent)
        def on_flow_started(source, event):
            broadcast({
                "type": "flow_started",
                "flow": getattr(event, "flow_name", None),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(FlowFinishedEvent)
        def on_flow_finished(source, event):
            broadcast({
                "type": "flow_finished",
                "flow": getattr(event, "flow_name", None),
                "timestamp": _ts(event),
            })

        # ── Flow method execution ─────────────────────────────────────────────

        @crewai_event_bus.on(MethodExecutionStartedEvent)
        def on_method_started(source, event):
            broadcast({
                "type": "method_execution_started",
                "flow": getattr(event, "flow_name", None),
                "method": getattr(event, "method_name", None),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(MethodExecutionFinishedEvent)
        def on_method_finished(source, event):
            broadcast({
                "type": "method_execution_finished",
                "flow": getattr(event, "flow_name", None),
                "method": getattr(event, "method_name", None),
                "timestamp": _ts(event),
            })

        @crewai_event_bus.on(MethodExecutionFailedEvent)
        def on_method_failed(source, event):
            broadcast({
                "type": "method_execution_failed",
                "flow": getattr(event, "flow_name", None),
                "method": getattr(event, "method_name", None),
                "error": str(getattr(event, "error", "")),
                "timestamp": _ts(event),
            })


# ---------------------------------------------------------------------------
# Module-level instantiation – registers all handlers immediately on import
# ---------------------------------------------------------------------------
ws_listener = WebSocketEventListener()

"""Custom CrewAI callbacks for streaming agent thoughts via WebSocket"""

import logging
from typing import Any, Dict, Optional
from crewai.telemetry import Telemetry

logger = logging.getLogger(__name__)


class WebSocketStreamCallback:
    """
    Callback handler that captures CrewAI events and streams them via WebSocket
    """
    
    def __init__(self, session_id: str, ws_manager):
        self.session_id = session_id
        self.ws_manager = ws_manager
        self.telemetry = Telemetry()
        
    async def on_agent_start(self, agent_name: str, task_description: str):
        """Called when an agent starts executing"""
        logger.info(f"Agent started: {agent_name}")
        await self.ws_manager.broadcast_thought(
            self.session_id,
            f"🤖 {agent_name}: Starting task - {task_description[:100]}..."
        )
        
    async def on_agent_finish(self, agent_name: str, output: str):
        """Called when an agent finishes execution"""
        logger.info(f"Agent finished: {agent_name}")
        await self.ws_manager.broadcast_thought(
            self.session_id,
            f"✅ {agent_name}: Task completed"
        )
        
    async def on_tool_start(self, tool_name: str, inputs: Dict[str, Any]):
        """Called when a tool starts executing"""
        logger.info(f"Tool started: {tool_name}")
        await self.ws_manager.broadcast_thought(
            self.session_id,
            f"🔧 Using tool: {tool_name}"
        )
        
    async def on_tool_end(self, tool_name: str, output: str):
        """Called when a tool finishes execution"""
        logger.info(f"Tool finished: {tool_name}")
        
    async def on_llm_start(self, prompt: str):
        """Called when LLM call starts"""
        logger.debug(f"LLM call started")
        await self.ws_manager.broadcast_thought(
            self.session_id,
            "💭 Thinking..."
        )
        
    async def on_llm_end(self, response: str):
        """Called when LLM call completes"""
        logger.debug(f"LLM call completed")
        
    async def on_task_start(self, task_description: str):
        """Called when a task starts"""
        logger.info(f"Task started: {task_description[:50]}")
        await self.ws_manager.broadcast_status_update(
            self.session_id,
            "researching",
            task_description[:50]
        )
        
    async def on_task_end(self, task_output: str):
        """Called when a task completes"""
        logger.info(f"Task completed")
        
    async def on_error(self, error: Exception):
        """Called when an error occurs"""
        logger.error(f"Error in agent execution: {error}")
        await self.ws_manager.broadcast_error(
            self.session_id,
            str(error)
        )

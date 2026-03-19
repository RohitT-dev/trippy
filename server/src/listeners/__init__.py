"""CrewAI event listeners package.

Importing this package causes ws_listener to register itself with the
CrewAI singleton event bus so all events are forwarded to WebSocket clients.
"""

from .websocket_listener import ws_listener, connected_clients, set_main_loop

__all__ = ["ws_listener", "connected_clients", "set_main_loop"]

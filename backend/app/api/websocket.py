"""
WebSocket Connection Manager for live task event broadcasting.
"""
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("web_agent.api.websocket")


class ConnectionManager:
    """
    Manages active WebSocket connections per task_id.
    """

    def __init__(self):
        # Maps task_id -> Set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)
        logger.info(f"WebSocket client connected to task {task_id}.")

    def disconnect(self, websocket: WebSocket, task_id: str):
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        logger.info(f"WebSocket client disconnected from task {task_id}.")

    async def broadcast_to_task(self, task_id: str, message: dict):
        if task_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[task_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception as e:
                    logger.debug(f"Error sending message to websocket: {e}")
                    disconnected.add(connection)
            for conn in disconnected:
                self.disconnect(conn, task_id)


ws_manager = ConnectionManager()

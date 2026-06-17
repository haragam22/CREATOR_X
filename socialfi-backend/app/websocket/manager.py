import logging
from fastapi import WebSocket
from typing import Dict, List
import json

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps creator_id to a list of active WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # Connections subscribed to global events (like market status)
        self.global_connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket, creator_id: int = None):
        await ws.accept()
        if creator_id is not None:
            if creator_id not in self.active_connections:
                self.active_connections[creator_id] = []
            self.active_connections[creator_id].append(ws)
            logger.info(f"Client subscribed to creator {creator_id}. Total: {len(self.active_connections[creator_id])}")
        else:
            self.global_connections.append(ws)
            logger.info(f"Client connected globally. Total global: {len(self.global_connections)}")

    def disconnect(self, ws: WebSocket, creator_id: int = None):
        if creator_id is not None:
            if creator_id in self.active_connections and ws in self.active_connections[creator_id]:
                self.active_connections[creator_id].remove(ws)
                logger.info(f"Client unsubscribed from creator {creator_id}.")
        else:
            if ws in self.global_connections:
                self.global_connections.remove(ws)
                logger.info("Global client disconnected.")

    async def broadcast(self, creator_id: int, message: dict):
        """Broadcast to clients subscribed to a specific creator, AND global clients"""
        msg_str = json.dumps(message)
        
        # Send to specific creator subscribers
        if creator_id in self.active_connections:
            for connection in list(self.active_connections[creator_id]):
                try:
                    await connection.send_text(msg_str)
                except Exception as e:
                    logger.error(f"Failed to send to client: {e}")
                    self.disconnect(connection, creator_id)
                    
        # Send to global subscribers as well
        for connection in list(self.global_connections):
            try:
                await connection.send_text(msg_str)
            except Exception as e:
                logger.error(f"Failed to send to global client: {e}")
                self.disconnect(connection)

    async def broadcast_all(self, message: dict):
        """Broadcast to ALL connected clients"""
        msg_str = json.dumps(message)
        
        # Broadcast globally
        for connection in list(self.global_connections):
            try:
                await connection.send_text(msg_str)
            except Exception as e:
                self.disconnect(connection)
                
        # Broadcast to all creator-specific subs
        for creator_id, connections in self.active_connections.items():
            for connection in list(connections):
                try:
                    await connection.send_text(msg_str)
                except Exception as e:
                    self.disconnect(connection, creator_id)

manager = ConnectionManager()

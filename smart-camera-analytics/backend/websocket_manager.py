"""
WebSocket Connection Manager for live dashboard updates.
Broadcasts CV Worker metadata to all connected dashboard clients.
"""
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # Map camera_id -> set of connected websockets
        self._camera_clients: Dict[int, Set[WebSocket]] = {}
        # Global subscribers (dashboard overview)
        self._global_clients: Set[WebSocket] = set()

    async def connect_global(self, ws: WebSocket):
        await ws.accept()
        self._global_clients.add(ws)
        logger.info(f"Global WS connected. Total global: {len(self._global_clients)}")

    async def connect_camera(self, ws: WebSocket, camera_id: int):
        await ws.accept()
        if camera_id not in self._camera_clients:
            self._camera_clients[camera_id] = set()
        self._camera_clients[camera_id].add(ws)
        logger.info(f"Camera {camera_id} WS connected. Total: {len(self._camera_clients[camera_id])}")

    def disconnect_global(self, ws: WebSocket):
        self._global_clients.discard(ws)

    def disconnect_camera(self, ws: WebSocket, camera_id: int):
        if camera_id in self._camera_clients:
            self._camera_clients[camera_id].discard(ws)

    async def broadcast_global(self, data: dict):
        """Send to all global subscribers."""
        message = json.dumps(data)
        dead = set()
        for ws in self._global_clients.copy():
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._global_clients.discard(ws)

    async def broadcast_camera(self, camera_id: int, data: dict):
        """Send to all subscribers of a specific camera."""
        message = json.dumps(data)
        dead = set()
        clients = self._camera_clients.get(camera_id, set()).copy()
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            if camera_id in self._camera_clients:
                self._camera_clients[camera_id].discard(ws)

    async def broadcast_alert(self, alert_data: dict):
        """Broadcast alerts to all connected clients."""
        payload = {"type": "alert", "data": alert_data}
        await self.broadcast_global(payload)

    @property
    def global_count(self) -> int:
        return len(self._global_clients)

    @property
    def camera_counts(self) -> Dict[int, int]:
        return {cid: len(ws_set) for cid, ws_set in self._camera_clients.items()}


# Singleton instance
manager = ConnectionManager()

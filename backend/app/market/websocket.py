from fastapi import WebSocket


class MarketWebSocketManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, symbol: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(symbol, []).append(websocket)

    async def broadcast(self, symbol: str, data: dict):
        for connection in self.connections.get(symbol, []):
            await connection.send_json(data)

    def disconnect(self, symbol: str, websocket: WebSocket):
        if symbol in self.connections and websocket in self.connections[symbol]:
            self.connections[symbol].remove(websocket)


manager = MarketWebSocketManager()

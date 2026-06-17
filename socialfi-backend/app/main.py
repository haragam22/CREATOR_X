from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, creators, market, portfolio, dashboard, sentiment
from app.tasks.event_listener import event_listener_daemon

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    listener_task = asyncio.create_task(event_listener_daemon())
    yield
    # Shutdown
    listener_task.cancel()

app = FastAPI(title="SocialFi Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(creators.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(dashboard.router)
app.include_router(sentiment.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to SocialFi API"}

from fastapi import WebSocket, WebSocketDisconnect
from app.websocket.manager import manager
import json

@app.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("action") == "subscribe":
                    creator_id = message.get("creator_id")
                    if creator_id:
                        # Re-register with specific creator_id
                        manager.disconnect(websocket)
                        await manager.connect(websocket, creator_id=creator_id)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        # We don't know the creator_id here easily without tracking it per-socket, 
        # so we rely on the manager's broadcast to clean up dead sockets automatically
        # or we just remove from global if it's there.
        manager.disconnect(websocket)


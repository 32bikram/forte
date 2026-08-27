from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from .routers import auth, user, websockets
from .config import settings
import redis
from .routers.websockets import lifespan

app = FastAPI(lifespan = lifespan)

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(websockets.router)

@app.get("/")
async def get():
    return "connected"
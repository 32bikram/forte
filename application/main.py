from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, logger
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, user, websockets, persistantDataShareing
from .config import settings
import redis, logging
from .routers.websockets import lifespan

logging.basicConfig(level=logging.INFO)
app = FastAPI(lifespan = lifespan)

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to your frontend's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(websockets.router)
app.include_router(persistantDataShareing.router)

@app.get("/")
async def get():
    return "connected"
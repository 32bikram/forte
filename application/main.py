from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from .routers import auth, user, websockets

app = FastAPI()

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(websockets.router)

@app.get("/")
async def get():
    return "hiiiiii"
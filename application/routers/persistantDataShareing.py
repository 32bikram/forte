from fastapi import FastAPI, APIRouter, WebSocket
from ..services.connection_manager import manager, ConnectionManager, LocalConnection
from . . import schemas

router = APIRouter(
    tags= ['Online Users']
)


def _user_rooms_key(username : str):
    return f"user:rooms:{username}"

@router.get("/online_users")
async def get_online_users():
    online_users = await manager.redis.hkeys("online_users:")
    return {"online_users":online_users}

@router.get("/connected_rooms")
async def get_connected_rooms(websocket:WebSocket, user_data : schemas.Userdata):
    rooms = await manager.redis.sget(_user_rooms_key(user_data.username))
    for room in rooms:
        manager.rooms.get(room,[]).append(LocalConnection(websocket, user_data))
    return {"connected_rooms":rooms}


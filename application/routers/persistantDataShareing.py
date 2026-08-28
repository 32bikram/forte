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

@router.get("/room_members", response_model = schemas.Rommmembers)
async def get_room_members(room_id :str):
    members = await manager.redis.hgetall(f"room:members:{room_id}")
    return {"room_id" : room_id,
            "members" : members
            }
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, APIRouter
from sqlalchemy.orm import Session
from pydantic import ValidationError
from . . import oauth2, schemas, database
from . .services.connection_manager import manager
import asyncio

@asynccontextmanager
async def lifespan(app : FastAPI):
    await manager.start_listner()
    yield

    if manager._listner_task:
        manager._listner_task.cancel()

        try:
            await manager._listner_task
        except asyncio.CancelledError:
            pass
        await manager.pubsub.close()
        await manager.redis.aclose()

router = APIRouter(
    tags = ['websocket']
)

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, 
    db : Session = Depends(database.get_db),
    client_info = Depends(oauth2.get_current_user_ws)
    ):

    username = client_info.username
    await manager.connect_global(websocket,username)

    async def validater(data, schema):
        try:
            new_data = schema.model_validate(data)
        except ValidationError:
            await websocket.send_json({
                "response" : "invalid data format"
            })
            return
        return new_data

    async def make_user_data(data):
        try:
            user_data=schemas.Userdata.model_validate({
                "username" : username,
                "room_id" : data["room_id"]
            })
        except ValidationError:
            await websocket.send_json({
                "response" : "improper data format"
            })
            return
        return user_data

    async def responder(schema : schemas.WebSocketResponse):
        await websocket.send_json(schema.model_dump())
        return schema.status == "ok"
        
    try:
        while True:
            data = await websocket.receive_json()
            if "type" not in data:
                await websocket.send_json({
                    "message" : "Invalid data format"
                })
                continue

            if data["type"] == "global message":
                new_data = await validater(data, schemas.GlobalMessage)
                if new_data is None:
                    continue
                response = await manager.broadcast_global(new_data.message, username)
                await responder(response)

            elif data["type"] == "create room":
                new_data = await validater(data, schemas.Datavalidate)
                user_data = await make_user_data(data)
                if new_data is None or user_data is None:
                    continue
                response = await manager.create_room(websocket, user_data)
                await responder(response)

            elif data["type"] == "join room":
                new_data = await validater(data, schemas.Datavalidate)
                user_data= await make_user_data(data)
                if new_data is None or user_data is None:
                    continue
                response = await manager.connect_local(websocket, user_data)
                await responder(response)

            elif data["type"] == "local message":
                new_data = await validater(data, schemas.MessageValidate)
                user_data= await make_user_data(data)
                if new_data is None or user_data is None:
                    continue
                response = await manager.broadcast_local(user_data, new_data.message)
                await responder(response)

            elif data["type"] == "disconnect Local":
                new_data = await validater(data, schemas.Datavalidate)
                user_data = await make_user_data(data)
                if new_data is None or user_data is None:
                    continue
                response = await manager.disconnect_local(websocket, user_data)
                await responder(response)

            elif data["type"] == "joinback rooms":
                await manager.get_connected_back_to_rooms(websocket, username)

            else:
                response = schemas.WebSocketResponse(status = "error", detail="invalid data format", action="data vlidation")
                await responder(response)

    except WebSocketDisconnect:
        await manager.disconnect_global(websocket, username)
        await manager.broadcast_global(f"{username} left the chat")
from fastapi import WebSocket, WebSocketException, status
import asyncio, json, logging
from . . import schemas
from . .config import settings
import redis.asyncio as redis

logger = logging.getLogger("jutustelu.connection_manager")

class LocalConnection:
    def __init__(self, websocket: WebSocket, user_data : schemas.Userdata):
        self.websocket = websocket
        self.user_data = user_data
#we wil pass this connection class object containing websoc, room_id, username, role to the connection manager

class GlobalConnection:
    def __init__(self, websocket:WebSocket, username: str):
        self.websocket = websocket
        self.username = username
# will be used for global connections no room id or role

ROOM_TTL = 86_400

def _room_members_key(room_id : str):
    return f"room:members:{room_id}"
def _user_rooms_key(username : str):
    return f"user:rooms:{username}"
def _room_host_key(room_id : str):
    return f"room:host:{room_id}"
GLOBAL_CHANNEL = "global_broadcast"
ONLINE_USERS = "online_users"
OFFLINE_USERS = "offline_users"
def _room_channel(room_id : str):
    return f"room:broadcast:{room_id}"

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[GlobalConnection] = []
        self.rooms: dict[str, list[LocalConnection]] = {} #room_id, {websoc,{username, role}}
        # self.user_rooms : dict[str, list[str]] = {} # username, li[room_id]
        # self.room_host : dict[str,str] = {} #mapping room : host
        self.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.pubsub = self.redis.pubsub()
        self._listner_task: asyncio.Task | None = None

    async def start_listner(self):
        await self.pubsub.subscribe(GLOBAL_CHANNEL)
        self._listner_task = asyncio.create_task(self._pubsub_listner_loop())

    async def _safe_send(slef, websocket:WebSocket, payload :dict):
    #handles the sending if data is not send handles the exception and return false to remove ws from active conn
        try:
            await websocket.send_json(payload)
            return True
        except:
            logger.warning("sending to websocket failed droping dead connection", exc_info =True)
            return False
    
    async def _pubsub_listner_loop(self):
        async for raw_data in self.pubsub.listen():
            if raw_data["type"] != "message":
                continue

            channel: str = raw_data["channel"] #global_channel/ room:broadcast:1234/ online_users/ offline_users
            payload : dict = json.loads(raw_data["data"])
            username : str = payload["username"]
            message : str = payload["data"]

            #storing the message in cache for later use 
            await self.redis.lpush(channel,payload)
            await self.redis.ltrim(channel,0,99)
            
            if channel == GLOBAL_CHANNEL:
                dead_connection =[]
                for conn in list(self.active_connections):
                    payload = {"channel":GLOBAL_CHANNEL, "username":username, "message":message}
                    if not await self._safe_send(conn.websocket, payload):
                        dead_connection.append(conn)
                #cleanup of socket
                for conn in dead_connection:
                    self.disconnect_global(conn.websocket,username)

            elif channel.startswith("room:broadcast:"):
                room_id : str = channel.removeprefix("room:broadcast:")
                dead_connection =[]
                for user in self.rooms.get(room_id,[]):
                    payload = {"channel" : room_id, "username":username, "message":message}
                    if not await self._safe_send(user.websocket, payload):
                        dead_connection.append(user)

                for conn in dead_connection:
                    self.disconnect_global(conn.websocket,username)

            elif channel == ONLINE_USERS:
                dead_connection = []
                payload = {"channel":ONLINE_USERS,"username":message}
                if not await self._safe_send(conn.websocket, payload):
                    dead_connection.append(conn)
                #cleanup of dead socket
                for conn in dead_connection:
                    self.disconnect_global(conn.websocket,username)

            elif channel == OFFLINE_USERS:
                dead_connection = []
                payload = {"channel":OFFLINE_USERS,"username":message}
                if not await self._safe_send(conn.websocket, payload):
                    dead_connection.append(conn)
                #cleanup of dead socket
                for conn in dead_connection:
                    self.disconnect_global(conn.websocket,username)

    async def connect_global(self, websocket: WebSocket, username : str):
        await websocket.accept()
        self.active_connections.append(GlobalConnection(websocket,username))
        #online status on
        count = await self.redis.hincrby("online_users:",username,1)
        payload = json.dumps({
            "channel" : ONLINE_USERS,
            "username" : username,
            "data" : "online"
        })
        await self.redis.publish(ONLINE_USERS,payload)

        #last 100 messages
        messages = await self.redis.lrange(GLOBAL_CHANNEL,0,99)
        messages.reverse()
        payload = {
            "type" : "message history",
            "room_id" : GLOBAL_CHANNEL,
            "messages" : [json.loads(message) for message in messages]
        }
        await websocket.send_json(payload)

    async def create_room(self, websocket:WebSocket, user_data : schemas.Userdata):
        room_host_key = _room_host_key(room_id=user_data.room_id)
        room_members_key = _room_members_key(user_data.room_id)
        user_room_key = _user_rooms_key(user_data.username)

        room_exists = await self.redis.exists(room_host_key)
        if room_exists:
            return schemas.WebSocketResponse(
                status="error", 
                detail="room with this id already exist",
                action = "create_room"
            )

        await self.redis.set(room_host_key,user_data.username, ex=ROOM_TTL)
        await self.redis.hset(room_members_key, user_data.username, "host")
        await self.redis.expire(room_members_key,ROOM_TTL) #setting expiry

        await self.redis.sadd(user_room_key, user_data.room_id)
        await self.redis.expire(user_room_key, ROOM_TTL)

        self.rooms[user_data.room_id]= [(LocalConnection(websocket, user_data))]

        await self.pubsub.subscribe(_room_channel(user_data.room_id))

        return schemas.WebSocketResponse(
            status="ok",
            detail="Room has been created",
            action = "create_room"
        )

    async def connect_local(self, websocket:WebSocket, user_data : schemas.Userdata):
        room_host_key = _room_host_key(user_data.room_id)
        user_room_key = _user_rooms_key(user_data.username)
        room_members_key = _room_members_key(user_data.room_id)
        room_channel = _room_channel(user_data.room_id)

        #room doesnt exist
        room_exists = await self.redis.exists(room_host_key)
        if not room_exists:
            return schemas.WebSocketResponse(
                status = "error",
                detail = "No room with this id exists",
                action = "connect_local"
            )
        #already member
        flag = await self.redis.sismember(user_room_key,user_data.room_id)
        if flag:
            return schemas.WebSocketResponse(
                status="error",
                detail = "already member of this room",
                action= "connect_local"
            )

        await self.redis.hset(room_members_key, user_data.username, "member")
        await self.redis.expire(room_members_key, ROOM_TTL)

        await self.redis.sadd(user_room_key, user_data.room_id)
        await self.redis.expire(user_room_key, ROOM_TTL)

        if user_data.room_id not in self.rooms:
            self.rooms[user_data.room_id] = []
        self.rooms[user_data.room_id].append(LocalConnection(websocket,user_data))

        await self.pubsub.subscribe(room_channel)

        await self._publish_to_room(user_data.room_id, f"{user_data.username} has joined the room", user_data.username)

        return schemas.WebSocketResponse(
                        status="ok",
                        detail = "successfully joined room",
                        action= "connect_local"
        )

    async def disconnect_local(self, websocket:WebSocket, user_data : schemas.Userdata):
        user_room_key = _user_rooms_key(user_data.username)
        room_host_key = _room_host_key(user_data.room_id)
        room_members_key = _room_members_key(user_data.room_id)

        room_exists = await self.redis.exists(room_host_key)
        if not room_exists:
            return schemas.WebSocketResponse(
                status = "error",
                detail = "no room with this id",
                action = "disconnect local"
            )
        if await self.redis.get(room_host_key) == user_data.username:
            members = await self.redis.hkeys(room_members_key)

            await self._publish_to_room(user_data.room_id, f"room with id:{user_data.room_id} has been deleted", user_data.username)
            for member in members:
                await self.redis.srem(_user_rooms_key(member),user_data.room_id)

            await self.redis.delete(room_host_key)
            await self.redis.delete(room_members_key)
            await self.pubsub.unsubscribe(_room_channel(user_data.room_id))
            #removing from local mem
            self.rooms.pop(user_data.room_id, None) #returns none if the key doesnt exist

            return schemas.WebSocketResponse(
                status = "ok",
                detail = "room is deleted",
                action = "disconnect_local"
            )

        else:
            members = await self.redis.hkeys(room_members_key) #getting all members
            await self.send_personal_message("you are leaving the room", websocket)
            await self._publish_to_room(user_data.room_id, f"{user_data.username} has left the room", username=user_data.username)
            await self.redis.srem(user_room_key, user_data.room_id)
            await self.redis.hdel(room_members_key, user_data.username)

            #local cleanup
            for user in self.rooms.get(user_data.room_id,[]).copy():
                if user.user_data.username == user_data.username:
                    self.rooms[user_data.room_id].remove(user)

        return schemas.WebSocketResponse(
            status="ok",
            detail="disconnected from the room",
            action="disconnect_local"
        )

    async def disconnect_global(self, websocket: WebSocket, username : str):

        for conn in self.active_connections:
            if conn.websocket==websocket:
                self.active_connections.remove(conn)
                break

        rooms = await self.redis.smembers(_user_rooms_key(username))
        for room in rooms:
            local_rooms = self.rooms.get(room,[])
            for local_room in local_rooms:
                if(local_room.websocket == websocket):
                    self.rooms[room].remove(local_room)
                    break


        count = await self.redis.hincrby("online_users:",username,-1)
        if count <= 0:
            await self.redis.hdel("online_users:",username)
            count = 0
            payload = json.dumps({
                "channel": OFFLINE_USERS,
                "username":username,
                "data" : "online"
            })
            await self.redis.publish(OFFLINE_USERS,payload)

    async def _publish_to_room(self, room_id : str, message : str, username :str):
        payload = json.dumps({"channel":_room_channel(room_id), "username":username ,"data":message})
        await self.redis.publish(_room_channel(room_id), payload)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_global(self, message: str, username : str):
        # for connection in self.active_connections:
        #     await connection.websocket.send_text(message)
        payload = json.dumps({"channel":GLOBAL_CHANNEL,"username":username, "data":message})
        await self.redis.publish(GLOBAL_CHANNEL, payload)

        return schemas.WebSocketResponse(
            status="ok",
            detail="successfully published message",
            action = "broadcast_global"
        )
    #when an user logs back in join him in the rooms he is connected
    async def get_connected_back_to_rooms(self, websocket:WebSocket, username):
        rooms = await self.redis.smembers(f"user:rooms:{username}")
        payload_list = []
        for room in rooms:
            user_data = schemas.Userdata(username=username,room_id=room)
            self.rooms.setdefault(room,[]).append(LocalConnection(websocket, user_data))
            #sending that rooms messages too
            channel = _room_channel(room)
            host = await self.redis.get(_room_host_key(room))
            is_host = False
            if(host==username):
                is_host = True
            messages = await self.redis.lrange(channel, 0, 99)
            messages.reverse()
            payload = {
                "type" : "message history",
                "room_id" : room,
                "host" : is_host,
                "messages" : [json.loads(message) for message in messages]
            }
            payload_list.append(payload)
        await websocket.send_json(payload_list)

    async def broadcast_local(self, user_data:schemas.Userdata, message:str):
        user_rooms_key = _user_rooms_key(user_data.username)
        flag = await self.redis.sismember(user_rooms_key, user_data.room_id)
        if not flag:
            return schemas.WebSocketResponse(
                status="ok",
                detail="You are not a member of this room",
                action = "broadcast_local"
            )
        
        await self._publish_to_room(user_data.room_id, message, user_data.username)
        return schemas.WebSocketResponse(status="ok", detail="successfully published message", action = "broadcast_local")

manager = ConnectionManager()
from fastapi import WebSocket, WebSocketException, status
from . . import schemas

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

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[GlobalConnection] = []
        self.rooms: dict[str, list[LocalConnection]] = {} #room_id, {websoc,{username, role}}
        self.user_rooms : dict[str, list[str]] = {} # username, li[room_id]
        self.room_host : dict[str,str] = {} #mapping room : host

    async def connect_global(self, websocket: WebSocket, username : str):
        await websocket.accept()
        self.active_connections.append(GlobalConnection(websocket,username))

    async def create_room(self, websocket:WebSocket, user_data : schemas.Userdata):
        if user_data.room_id not in self.rooms:
            self.room_host[user_data.room_id] = user_data.username
            self.rooms[user_data.room_id] =[]
            self.rooms[user_data.room_id].append(LocalConnection(websocket,user_data))
        
            #mainting the rooms user joined
            if user_data.username not in self.user_rooms:
                self.user_rooms[user_data.username] = []
            self.user_rooms[user_data.username].append(user_data.room_id)
        else:
            return "room with this id already exist"
        

    async def connect_local(self, websocket:WebSocket, user_data : schemas.Userdata):
        #checking if user is already in that room
        rooms_user_joined = self.user_rooms.get(user_data.username,[]) #if user not in any room we will get key error
        if user_data.room_id in rooms_user_joined:
            return "You are already a member of this room"
        
        #the creation of room
        if user_data.room_id not in self.rooms:
            return "There is no room with this id"
        self.rooms[user_data.room_id].append(LocalConnection(websocket,user_data))

        #mainting the rooms user joined
        if user_data.username not in self.user_rooms:
            self.user_rooms[user_data.username] = []
        self.user_rooms[user_data.username].append(user_data.room_id)

        for member in self.rooms[user_data.room_id]:
            await self.send_personal_message(f"{user_data.username} has joined", member.websocket)

    async def disconnect_global(self, websocket: WebSocket, username : str):
        #removing him from the rooms he joined
        for room_ids in self.user_rooms.get(username,[]).copy(): #reason in doc 1, user might not be in any room so chance of key error
            await self.disconnect_local(websocket, schemas.Userdata(username,room_ids))

        self.user_rooms.pop(username,None) #if exist then delete else skip
            

        for conn in self.active_connections:
            if conn.websocket==websocket:
                self.active_connections.remove(conn)
                break

    async def disconnect_local(self, websocket:WebSocket, user_data : schemas.Userdata):
        if user_data.room_id in self.rooms:
            if(self.room_host[user_data.room_id]==user_data.username):
                for member in self.rooms[user_data.room_id]:
                    if member.user_data.username != user_data.username: #skipping notifying the host
                        await self.send_personal_message(f"room with id {user_data.room_id} was deleted", member.websocket)

                    self.user_rooms[member.user_data.username].remove(member.user_data.room_id) #removing the room from users personal room list too

                del self.rooms[user_data.room_id]
                del self.room_host[user_data.room_id]

            else:
                for members in self.rooms[user_data.room_id]:
                    if(members.user_data.username == user_data.username):
                        await self.send_personal_message("you are leaving the room", members.websocket)
                        self.rooms[user_data.room_id].remove(members)
                        if user_data.room_id in self.user_rooms[user_data.username]: #removing that room from users own list
                            self.user_rooms.get(user_data.username,[]).remove(user_data.room_id)
                        break

                for member in self.rooms[user_data.room_id].copy():
                    await self.send_personal_message(f"{user_data.username} has left", member.websocket)
        else:
            return "No room with this id exist"

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_global(self, message: str):
        for connection in self.active_connections:
            await connection.websocket.send_text(message)

    async def broadcast_local(self, user_data:schemas.Userdata, message:str):
        if user_data.room_id in self.user_rooms.get(user_data.username,[]):
            for local_player in self.rooms.get(user_data.room_id,[]):
                await local_player.websocket.send_text(message)
        else:
            return "You are not a member of this room"

manager = ConnectionManager()
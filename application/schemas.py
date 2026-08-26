from pydantic import BaseModel, EmailStr, ConfigDict
from fastapi import WebSocket

class User(BaseModel):
    username : str
    password : str
    email : EmailStr

class ReturnUser(BaseModel):
    username : str
    response : str

class JWTData(BaseModel):
    access_token : str
    token_type : str

class TokenData(BaseModel):
    id : int

class Userdata(BaseModel):
    username : str
    room_id : str
    role : str = "member"

class Datavalidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id : str
    type : str

class MessageValidate(Datavalidate):
    message : str

class GlobalMessage(BaseModel):
    type : str
    message : str
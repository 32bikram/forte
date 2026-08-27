from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status, WebSocket, WebSocketException, Request
from . import schemas, models, database
from sqlalchemy.orm import Session
from .config import settings

oauth2_schema = OAuth2PasswordBearer(tokenUrl="login", auto_error=False) #autoerror false so it doesnt throw error befor we check cookie
#it tells from the login function we will get the token

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
def get_token_from_request(request : Request, header_token : str | None):
    token = header_token or request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code= status.HTTP_401_UNAUTHORIZED,
            detail = "couldnt validate token"
        )
    return token

def create_access_token(data : dict):
    to_encode = data.copy() #we dont wanna change the actual data
    expire = datetime.now(timezone.utc)+timedelta(minutes = ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp" : expire})    # the key exp here is standard dont change it

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm = ALGORITHM)  #payload,secretke,algo
    return encoded_jwt

def verify_access_token(token : str, credential_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms = [ALGORITHM])
        id : int = payload.get("id")
        if id is None:
            raise credential_exception
        token_data = schemas.TokenData(id = id)
        #creates a pydantic object of TokenData class with the id retrived from payload
    except JWTError:
        raise credential_exception
    
    return token_data

def get_current_user(request : Request, token : str = Depends(oauth2_schema), db : Session = Depends(database.get_db)):
    token = get_token_from_request(request, token)
    credential_exception = HTTPException(status_code = status.HTTP_401_UNAUTHORIZED, detail = "couldnt validate credentials",
                                         headers = {"WWW-Authenticate":"Bearer"})
    token = verify_access_token(token, credential_exception)

    user = db.query(models.Users).filter(models.Users.user_id == token.id).first()
    return user

def get_current_user_ws(websocket: WebSocket, db: Session = Depends(database.get_db)):
    token = websocket.cookies.get("access_token")
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    credential_exception = WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    token_data = verify_access_token(token, credential_exception)

    user = db.query(models.Users).filter(models.Users.user_id == token_data.id).first()
    if user is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    return user
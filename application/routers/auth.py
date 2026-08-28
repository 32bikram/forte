from fastapi import APIRouter, HTTPException, Depends, status, Response
from sqlalchemy.orm import Session
from fastapi.security.oauth2 import OAuth2PasswordRequestForm #it is a class that creates an obj with recived data
#the reason OAuth2PasswordRequestForm is used not direct pydantic, The reason is that the OAuth2 specification requires
# the login credentials to be sent as form data, not JSON.
from .. import database, schemas, models, utils, oauth2

router = APIRouter(
    tags = ['Authentication']
)

@router.post("/login", response_model = schemas.JWTData)
def getUser(response : Response, user : OAuth2PasswordRequestForm = Depends(), db : Session = Depends(database.get_db)):
    user_credentials =  db.query(models.Users).filter(models.Users.username == user.username).first()
    #since we are using form and it only has field username, password so the email we are passing will be given the name - username
    if user_credentials is None:
        raise HTTPException(status_code = status.HTTP_403_FORBIDDEN, detail = f"no user named {user.username}")
    if utils.match_pwd(user.password, user_credentials.password) == False:
        raise HTTPException(status_code = status.HTTP_403_FORBIDDEN, detail = "Wrong Username or Password")
    
    access_token = oauth2.create_access_token(data = {"id" : user_credentials.user_id})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,     # It means JavaScript running in the browser cannot access this cookie.
        secure=True,       # Only send this cookie over HTTPS.
        samesite="none",    # "strict" blocks it if frontend/backend are different domains
        max_age=60 * 60,   # 3600 sec
    )
    return {"access_token": access_token, "token_type" : "bearer"}
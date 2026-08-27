from fastapi import status, HTTPException, Depends,APIRouter
from sqlalchemy.orm import Session
from .. import models, schemas, utils
from ..database import get_db

router = APIRouter(
    tags= ['Account Creation']
)

@router.post("/createuser", status_code = status.HTTP_201_CREATED, response_model = schemas.ReturnUser)
def createUser(user : schemas.User, db : Session = Depends(get_db)):
    existing_user = db.query(models.Users).filter(models.Users.username == user.username).first()
    if existing_user is not None:
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail = "user with same credential exist"
        )
    user.password = utils.hash(user.password)
    try:
        res = models.Users(**user.model_dump())  #users = actual schema or table
        db.add(res)
        db.commit()
        db.refresh(res)
    except:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = "Please try again after some time"
        )
    res.response = "Account created, you are ready to fight"
    return res


@router.get("/getuser/{username}", response_model = schemas.ReturnUser)
def getUser(username : str, db : Session = Depends(get_db)):
    res = db.query(models.Users).filter(models.Users.username == username).first()
    if res is None:
         raise HTTPException(
          status_code = status.HTTP_404_NOT_FOUND,   
          detail = f"no user name {username}"
         )
    res.reponse = "ok"
    return res

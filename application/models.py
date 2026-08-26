from sqlalchemy import Column, Integer, String
from .database import Base

class Users(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key = True, nullable = False)
    username = Column(String, nullable=False)
    password = Column(String, nullable = False)
    email = Column(String, nullable = False)
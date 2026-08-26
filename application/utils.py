from passlib.context import CryptContext

pwd_context = CryptContext(schemes = ["bcrypt"],deprecated = "auto") #tells what kinda encryption to use
def hash(password):
    return pwd_context.hash(password) #to hash the password

def match_pwd(user_pw, hash_pw):
    return pwd_context.verify(user_pw, hash_pw)
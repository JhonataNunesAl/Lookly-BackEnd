from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import HTTPException
from core.config import settings
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()

_blocklist = set()

def get_password_hash(senha: str) -> str:
    return ph.hash(senha)

def verify_password(senha_plana: str, senha_hash: str) -> bool:
    try:
        return ph.verify(senha_hash, senha_plana)
    except VerifyMismatchError:
        return False

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=8)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def revoke_token(jti: str):
    _blocklist.add(jti)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        jti = payload.get("jti")

        if jti in _blocklist:
            raise HTTPException(status_code=401, detail="Token revogado")

        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
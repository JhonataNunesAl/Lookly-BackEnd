from fastapi import Request, HTTPException
from core.security import verify_token


def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if not auth:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    token = auth.replace("Bearer ", "")
    return verify_token(token)
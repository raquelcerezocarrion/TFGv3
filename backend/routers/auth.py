from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta

from backend.memory import state_store
from backend.core.config import settings

import hashlib
import hmac
import os
import jwt

router = APIRouter()

class RegisterIn(BaseModel):
    email: str
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None

class LoginIn(BaseModel):
    email: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

def _hash_password(password: str) -> str:
    # simple salted hash using sha256 (sufficient for demo); for prod use passlib/bcrypt
    salt = settings.APP_NAME[:8].encode('utf-8')
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000).hex()

def _verify_password(password: str, hashed: str) -> bool:
    return hmac.compare_digest(_hash_password(password), hashed)

def _create_token(data: dict, expires_minutes: int = 60*24) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.APP_NAME, algorithm="HS256")


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn):
    # basic email sanity check
    if "@" not in payload.email:
        raise HTTPException(status_code=400, detail="Email inválido")
    existing = state_store.get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Usuario ya existe")
    hashed = _hash_password(payload.password)
    user = state_store.create_user(payload.email, hashed, payload.full_name)
    token = _create_token({"sub": user.email, "user_id": user.id})
    return {"access_token": token}


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn):
    user = state_store.get_user_by_email(payload.email)
    if not user or not _verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = _create_token({"sub": user.email, "user_id": user.id})
    return {"access_token": token}

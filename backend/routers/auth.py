from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext

from backend.memory import state_store
from backend.core.config import settings

import hashlib
import hmac
import os
import jwt

router = APIRouter()

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Use pbkdf2_sha256 for hashing in tests/environments where bcrypt backend
# detection can fail due to system-specific bcrypt builds. pbkdf2_sha256 is
# widely available and secure for this application's testing purposes.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def _hash_password(password: str) -> str:
    # Use passlib bcrypt for password hashing
    return pwd_context.hash(password)


def _verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def _create_token(data: dict, expires_minutes: int = 60*24) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn):
    # Normalize email and delegate validation to Pydantic's EmailStr
    email = payload.email.lower().strip()
    existing = state_store.get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=400, detail="Usuario ya existe")
    hashed = _hash_password(payload.password)
    user = state_store.create_user(email, hashed, payload.full_name)
    token = _create_token({"sub": user.email, "user_id": user.id})
    # devolvemos el token y el tipo para que el frontend no tenga que adivinar
    # Devuelvo token y tipo. El frontend lo guarda y lo usa en Authorization.
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn):
    email = payload.email.lower().strip()
    user = state_store.get_user_by_email(email)
    if not user or not _verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = _create_token({"sub": user.email, "user_id": user.id})
    # Todo correcto: devuelvo el token. Si más tarde queremos refresh tokens,
    # podemos hacerlo aquí.
    return {"access_token": token, "token_type": "bearer"}

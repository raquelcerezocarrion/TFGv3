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
    # Hash sencillo con salt para la demo. Si esto fuera un producto real,
    # me pondría a usar passlib o bcrypt y no este apaño casero.
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000).hex()

def _verify_password(password: str, hashed: str) -> bool:
    # Comparo de forma segura para evitar ataques de timing; la función de
    # hashing es la misma que la de arriba, así que comprobamos igualdad.
    return hmac.compare_digest(_hash_password(password), hashed)

def _create_token(data: dict, expires_minutes: int = 60*24) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.APP_NAME, algorithm="HS256")


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn):
    # basic email sanity check
    # Comprobación mínima del email (esto no valida todo, pero evita obviedades)
    if "@" not in payload.email:
        raise HTTPException(status_code=400, detail="Email inválido")
    existing = state_store.get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Usuario ya existe")
    hashed = _hash_password(payload.password)
    user = state_store.create_user(payload.email, hashed, payload.full_name)
    token = _create_token({"sub": user.email, "user_id": user.id})
    # devolvemos el token y el tipo para que el frontend no tenga que adivinar
    # Devuelvo token y tipo. El frontend lo guarda y lo usa en Authorization.
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn):
    user = state_store.get_user_by_email(payload.email)
    if not user or not _verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = _create_token({"sub": user.email, "user_id": user.id})
    # Todo correcto: devuelvo el token. Si más tarde queremos refresh tokens,
    # podemos hacerlo aquí.
    return {"access_token": token, "token_type": "bearer"}

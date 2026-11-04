from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import schemas
from app.config import get_settings
from app.models import User
from app.security import CurrentUser, Db, authenticate_password, create_access_token, password_hash

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=schemas.UserOut, status_code=201)
def register(payload: schemas.Register, db: Db):
    user = User(name=payload.name, email=str(payload.email), password_hash=password_hash.hash(payload.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email is already registered") from None
    return user


@router.post("/login", response_model=schemas.Token)
def login(payload: schemas.Login, db: Db):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not authenticate_password(payload.password, user.password_hash if user else None):
        raise HTTPException(401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    return schemas.Token(access_token=create_access_token(user.id), expires_in=get_settings().access_token_minutes * 60)


@router.get("/me", response_model=schemas.UserOut)
def me(user: CurrentUser):
    return user

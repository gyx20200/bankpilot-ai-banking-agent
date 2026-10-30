"""Day 7 auth gateway: only Java authenticates users and issues/revokes tokens."""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from app import banking_client as bank

router = APIRouter(prefix="/api/agent/auth", tags=["Auth"])


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)
    fullName: str = Field(min_length=1, max_length=50)
    phone: str = Field(pattern=r"^1[3-9][0-9]{9}$")


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


def _fail(exc: bank.BankError):
    raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/register", status_code=201)
async def register(body: RegisterBody):
    try:
        return await bank.register_user(body.model_dump())
    except bank.BankError as exc:
        _fail(exc)


@router.post("/login")
async def login(body: LoginBody):
    try:
        return await bank.login_user(body.username, body.password)
    except bank.BankError as exc:
        _fail(exc)


@router.get("/me")
async def me(authorization: str | None = Header(default=None)):
    try:
        return await bank.current_user(authorization)
    except bank.BankError as exc:
        _fail(exc)


@router.post("/logout")
async def logout(authorization: str | None = Header(default=None)):
    try:
        return await bank.logout_user(authorization)
    except bank.BankError as exc:
        _fail(exc)

import random
import string

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.database import db_session
from utils.password_utils import encrypt_password, verify_password

router = APIRouter()


def generate_random_pwd(length: int = 8) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


class CreateEmployeeRequest(BaseModel):
    emp_username: str = Field(..., min_length=3)
    admin_username: str = Field(...)
    admin_password: str = Field(...)


@router.post("/create-employee", summary="Create an employee account")
async def create_employee(request: CreateEmployeeRequest):
    with db_session() as conn:
        admin = conn.execute(
            "SELECT password, role FROM user_info WHERE username = ?",
            (request.admin_username,),
        ).fetchone()

        if not admin:
            raise HTTPException(status_code=401, detail="Admin username does not exist")
        if admin["role"] != "admin":
            raise HTTPException(status_code=403, detail="Only admins can create employee accounts")
        if not verify_password(request.admin_password, admin["password"]):
            raise HTTPException(status_code=401, detail="Admin password is incorrect")

        raw_pwd = generate_random_pwd()
        hashed_pwd = encrypt_password(raw_pwd)

        try:
            conn.execute(
                """
                INSERT INTO user_info (username, password, role, is_first_login)
                VALUES (?, ?, ?, 1)
                """,
                (request.emp_username, hashed_pwd, "employee"),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=400, detail="Username already exists") from exc
            raise

    return {
        "code": 200,
        "msg": "Success",
        "data": {
            "emp_username": request.emp_username,
            "initial_pwd": raw_pwd,
            "tips": "The employee must change this password on first login",
        },
    }


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


@router.post("/login", summary="User login")
async def login(request: LoginRequest):
    with db_session() as conn:
        user = conn.execute(
            "SELECT password, role, is_first_login FROM user_info WHERE username = ?",
            (request.username,),
        ).fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="Username does not exist")
    if not verify_password(request.password, user["password"]):
        raise HTTPException(status_code=401, detail="Password is incorrect")

    return {
        "code": 200,
        "msg": "Success",
        "data": {
            "username": request.username,
            "role": user["role"],
            "is_first_login": bool(user["is_first_login"]),
        },
    }


class ChangePwdRequest(BaseModel):
    username: str = Field(...)
    old_pwd: str = Field(...)
    new_pwd: str = Field(..., min_length=8)


@router.post("/change-pwd", summary="Change password")
async def change_pwd(request: ChangePwdRequest):
    with db_session() as conn:
        user = conn.execute(
            "SELECT password FROM user_info WHERE username = ?",
            (request.username,),
        ).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail=f"Username {request.username} does not exist")
        if not verify_password(request.old_pwd, user["password"]):
            raise HTTPException(status_code=400, detail="Old password is incorrect")
        if verify_password(request.new_pwd, user["password"]):
            raise HTTPException(status_code=400, detail="New password must be different from old password")

        conn.execute(
            """
            UPDATE user_info
            SET password = ?, is_first_login = 0
            WHERE username = ?
            """,
            (encrypt_password(request.new_pwd), request.username),
        )

    return {
        "code": 200,
        "msg": "Password updated successfully",
        "data": {"username": request.username},
    }

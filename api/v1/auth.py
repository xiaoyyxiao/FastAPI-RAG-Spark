# api/v1/auth.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import sqlite3
import random
import string
from utils.password_utils import encrypt_password, verify_password

router = APIRouter()

# 生成随机初始密码
def generate_random_pwd(length=8) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# 1. 创建员工账户
class CreateEmployeeRequest(BaseModel):
    emp_username: str = Field(..., min_length=3)
    admin_username: str = Field(...)
    admin_password: str = Field(...)

@router.post("/create-employee", summary="管理员创建员工账户")
async def create_employee(request: CreateEmployeeRequest):
    conn = sqlite3.connect("docs.db")
    cursor = conn.cursor()
    try:
        # 分步校验管理员（报错信息更精准）
        cursor.execute("SELECT password, role FROM user_info WHERE username = ?", (request.admin_username,))
        admin = cursor.fetchone()
        
        if not admin:
            raise HTTPException(status_code=401, detail="管理员用户名不存在")
        if admin[1] != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可创建员工账户")
        if not verify_password(request.admin_password, admin[0]):
            raise HTTPException(status_code=401, detail="管理员密码错误")
        
        # 生成员工密码并创建账户
        raw_pwd = generate_random_pwd()
        hashed_pwd = encrypt_password(raw_pwd)
        cursor.execute(
            "INSERT INTO user_info (username, password, role, is_first_login) VALUES (?, ?, ?, 1)",
            (request.emp_username, hashed_pwd, "employee")
        )
        conn.commit()
        return {
            "code": 200,
            "msg": "创建成功",
            "data": {
                "emp_username": request.emp_username,
                "initial_pwd": raw_pwd,
                "tips": "员工首次登录需修改密码"
            }
        }
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="用户名已存在（需唯一）")
    finally:
        conn.close()

# 2. 登录接口
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)

@router.post("/login", summary="用户登录")
async def login(request: LoginRequest):
    conn = sqlite3.connect("docs.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT password, role, is_first_login FROM user_info WHERE username = ?", (request.username,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="用户名不存在")
        if not verify_password(request.password, user[0]):
            raise HTTPException(status_code=401, detail="密码错误")
        
        return {
            "code": 200,
            "msg": "登录成功",
            "data": {
                "username": request.username,
                "role": user[1],
                "is_first_login": bool(user[2])
            }
        }
    finally:
        conn.close()

# 3. 改密接口
# api/v1/auth.py - 替换原有change_pwd函数
# 3. 改密接口
class ChangePwdRequest(BaseModel):
    username: str = Field(...)
    old_pwd: str = Field(...)
    new_pwd: str = Field(..., min_length=8)

@router.post("/change-pwd", summary="修改密码")
async def change_pwd(request: ChangePwdRequest):
    conn = sqlite3.connect("docs.db")
    cursor = conn.cursor()
    try:
        # 1. 先查用户是否存在（补充精准报错）
        cursor.execute("SELECT username, password, role FROM user_info WHERE username = ?", (request.username,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"用户名【{request.username}】不存在")
        
        # 2. 校验旧密码（明确提示是哪个用户的密码错）
        if not verify_password(request.old_pwd, user[1]):
            raise HTTPException(
                status_code=400, 
                detail=f"用户【{request.username}】的旧密码错误（管理员初始密码：admin123456；员工初始密码是创建时返回的随机密码）"
            )
        
        # 3. 避免新密码和旧密码一致（补充优化）
        if verify_password(request.new_pwd, user[1]):
            raise HTTPException(status_code=400, detail="新密码不能和旧密码一致")
        
        # 4. 更新密码并标记为非首次登录
        new_hashed_pwd = encrypt_password(request.new_pwd)
        cursor.execute(
            "UPDATE user_info SET password = ?, is_first_login = 0 WHERE username = ?",
            (new_hashed_pwd, request.username)
        )
        conn.commit()
        
        return {
            "code": 200,
            "msg": f"用户【{request.username}】密码修改成功，请重新登录",
            "data": {"username": request.username}
        }
    finally:
        conn.close()
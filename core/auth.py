# core/auth.py
from datetime import timedelta, datetime
from fastapi import Depends, HTTPException, status, FastAPI, UploadFile, File
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from config.settings import settings
import logging
import string
import random
# 配置
from config.settings import settings

# 密码哈希
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")  # 无额外依赖，无长度限制
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# 定义User模型
class User(BaseModel):
    username: str
    disabled: bool = False

    class Config:
        from_attributes = True  # 替代Pydantic 1.x的orm_mode（避免警告）

def generate_strong_password(length: int = 16) -> str:    # 随机生成密码
    # 定义安全的字符集（排除易混淆字符）
    lowercase = string.ascii_lowercase.replace('l', '').replace('o', '')
    uppercase = string.ascii_uppercase.replace('I', '').replace('O', '')
    digits = string.digits.replace('0', '').replace('1', '')
    symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    # 确保密码包含至少每种类型的字符
    password = [
        random.choice(lowercase),
        random.choice(uppercase),
        random.choice(digits),
        random.choice(symbols)
    ]
    
    # 填充剩余长度并打乱
    all_chars = lowercase + uppercase + digits + symbols
    password += random.choices(all_chars, k=length - 4)
    random.shuffle(password)
    
    return ''.join(password)

# 工具函数：验证密码
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# 工具函数：生成 token
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# 依赖项：获取当前用户
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    # 认证失败异常
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:    # 解码JWT
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    # 验证用户存在
    user = fake_users_db.get(username)
    if user is None:
        raise credentials_exception
    return User(**user)

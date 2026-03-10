# utils/password_utils.py
import bcrypt

# 加密密码（不可逆，企业级必用）
def encrypt_password(raw_pwd: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(raw_pwd.encode('utf-8'), salt)
    return hashed.decode('utf-8')

# 验证密码（登录时用）
def verify_password(raw_pwd: str, hashed_pwd: str) -> bool:
    return bcrypt.checkpw(raw_pwd.encode('utf-8'), hashed_pwd.encode('utf-8'))
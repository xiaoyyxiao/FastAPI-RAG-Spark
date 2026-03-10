# 配置项统一管理，支持环境变量注入
import os
from pydantic_settings import BaseSettings
from datetime import timedelta

class Settings(BaseSettings):
    # FastAPI
    APP_TITLE: str = "企业级智能文档问答系统"
    APP_VERSION: str = "1.0"
    
    # 远程Redis
    REDIS_HOST: str = "redis-12345.c10.us-east-1-2.ec2.redns.redis-cloud.com"  # 示例地址，可搜“免费Redis测试实例”找可用的
    REDIS_PORT: int = 12345  # 对应端口
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: str = "你的测试实例密码"
    REDIS_EXPIRE_SECONDS: int = 600
    REDIS_SSL: bool = True

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-1234567890-abcdefghijklmnopqrstuvwxyz")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # 讯飞星火API配置
    XF_APPID: str = os.getenv("XF_APPID", "96d8b7d6")
    XF_APISecret: str = os.getenv("XF_APISecret", "MmVmMTgyYzg3NDZjNWZhNGVkNzVhNTE0")
    XF_APIKey: str = os.getenv("XF_APIKey", "bc4d48ac6d3684e4b098d0ac991d4ccf")
    XF_DOMAIN: str = "lite"  
    XF_URL: str = "https://spark-api-open.xf-yun.com/v1/chat/completions"  # 接口地址
    # XF_URL = "https://spark-api-open.xf-yun.com/v1/chat/completions"
    # 文档上传限制
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: list = ["txt","pdf", "docx"]

#实例化配置，整个项目共用
settings = Settings()
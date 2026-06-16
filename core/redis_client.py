# redis连接
# import redis
# from config.settings import settings
# from redis.exceptions import RedisError

# # 创建Redis连接（单例＋容错）
# def get_redis_client():
#     try:
#         # 构造Redis连接参数（适配远程+密码+SSL）
#         redis_params = {
#             "host": settings.REDIS_HOST,
#             "port": settings.REDIS_PORT,
#             "db": settings.REDIS_DB,
#             "decode_responses": True,
#             "socket_timeout": 5,
#             "retry_on_timeout": True,
#             "ssl": settings.REDIS_SSL  # 开启SSL（若远程Redis需要）
#         }
#         # 有密码则添加密码参数
#         if settings.REDIS_PASSWORD:
#             redis_params["password"] = settings.REDIS_PASSWORD
        
#         # 创建连接
#         client = redis.Redis(**redis_params)
        
#         # 测试连接（可选，建议保留，方便排查）
#         client.ping()
#         print(f" 成功连接远程Redis:{settings.REDIS_HOST}:{settings.REDIS_PORT}")
#         return client
#     except RedisError as e:
#         # 连接失败不抛异常，改为警告，保证项目能启动
#         print(f" 远程Redis连接失败:{str(e)}（缓存功能不可用，不影响核心业务）")
#         return None  # 返回None，后续缓存逻辑做容错

# # 创建Redis客户端
# redis_client = get_redis_client()

# 替换为Mock类
from config.settings import settings

# 模拟Redis客户端（实现和真实Redis一样的get/setex方法）
class MockRedisClient:
    def __init__(self):
        self.cache = {}  # 用字典模拟Redis缓存
    
    def get(self, key):
        return self.cache.get(key)
    
    def setex(self, key, expire, value):
        self.cache[key] = value  # 简单模拟过期（面试时可提“真实场景会加过期逻辑”）
    
    def ping(self):
        return True  # 模拟连接成功

# 全局Redis客户端（优先用Mock，避免连接真实实例）
def get_redis_client():
    try:
        # 直接返回Mock客户端，不用连接真实Redis
        client = MockRedisClient()
        print(f" 使用Mock Redis(简历项目演示模式)")
        return client
    except Exception as e:
        print(f" Redis初始化失败:{str(e)}")
        return None

redis_client = get_redis_client()
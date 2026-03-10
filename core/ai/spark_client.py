# spark_client.py
import requests
from config.settings import settings

class SparkClient:

    def ask(self, question: str):
        # 【关键修改 1】：使用标准 Bearer 认证，密码通常是 APIKey 和 APISecret 的组合拼接
        api_password = f"{settings.XF_APIKey}:{settings.XF_APISecret}"
        headers = {
            "Authorization": f"Bearer {api_password}",
            "Content-Type": "application/json"
        }

        # 【关键修改 2】：去除 appid 等非标准字段，使用纯 OpenAI 兼容的 Payload
        data = {
            "model": "lite",  # 对于 lite 版本，模型传 "lite" 或 "spark-lite" 均可
            "messages": [
                {
                    "role": "user",
                    "content": question
                }
            ],
            "temperature": 0.5
        }

        # 添加完整的网络异常捕获
        try:
            resp = requests.post(
                settings.XF_URL,
                headers=headers,
                json=data,
                timeout=30
            )
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求讯飞服务器失败 (Host/网络异常): {str(e)}")

        # 检查 HTTP 状态码（处理 401 鉴权失败、404 等问题）
        if resp.status_code != 200:
            raise Exception(f"AI 接口报错，状态码: {resp.status_code}, 详情: {resp.text}")

        result = resp.json()
        print("讯飞返回:", result)

        # 处理 API 返回的业务错误
        if "error" in result and result["error"]:
            raise Exception(str(result["error"]))

        choices = result.get("choices", [])
        if not choices:
            raise Exception("AI未返回内容")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        if not content:
            raise Exception("AI回答为空")

        return content

spark_client = SparkClient()
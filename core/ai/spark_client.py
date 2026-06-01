import requests

from config.settings import settings


class SparkClient:
    def ask(self, question: str) -> str:
        if not settings.XF_APIKey or not settings.XF_APISecret:
            raise Exception(
                "Spark credentials are missing. Set XF_APIKey and XF_APISecret in .env."
            )

        headers = {
            "Authorization": f"Bearer {settings.XF_APIKey}:{settings.XF_APISecret}",
            "Content-Type": "application/json",
        }
        data = {
            "model": settings.XF_MODEL,
            "messages": [{"role": "user", "content": question}],
            "temperature": 0.5,
        }

        try:
            response = requests.post(
                settings.XF_URL,
                headers=headers,
                json=data,
                timeout=30,
            )
        except requests.exceptions.RequestException as exc:
            raise Exception(f"Failed to reach Spark API: {exc}") from exc

        if response.status_code != 200:
            raise Exception(
                f"Spark API error {response.status_code}: {response.text}"
            )

        result = response.json()
        if result.get("error"):
            raise Exception(str(result["error"]))

        choices = result.get("choices", [])
        if not choices:
            raise Exception("Spark API returned no choices.")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise Exception("Spark API returned an empty answer.")

        return content


spark_client = SparkClient()

import json
import logging
from typing import AsyncIterator
from backend.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        import httpx
        self._client = httpx.AsyncClient(
            base_url=settings.AI_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.AI_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    async def chat(self, messages: list[dict]) -> str:
        if not settings.AI_API_KEY:
            return "[AI_API_KEY 未配置，请在 .env 中设置]"

        resp = await self._client.post(
            "/chat/completions",
            json={
                "model": settings.AI_MODEL,
                "messages": messages,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        if not settings.AI_API_KEY:
            yield "[AI_API_KEY 未配置，请在 .env 中设置]"
            return

        async with self._client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": settings.AI_MODEL,
                "messages": messages,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError):
                    continue

    async def close(self):
        await self._client.aclose()

    def reload(self):
        """配置变更后重建客户端（热更新，无需重启）"""
        import httpx
        self._client = httpx.AsyncClient(
            base_url=settings.AI_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.AI_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        logger.info("LLM 客户端已重建（配置热更新）")


llm_service = LLMService()

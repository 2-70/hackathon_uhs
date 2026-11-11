"""Small real generation probe used only by the local preview launcher."""

import asyncio

import httpx

from .gemini import THINKING_LEVEL_BY_MODEL, GeminiError, describe_http_error


async def check_connection(api_key: str | None, model: str, transport=None) -> None:
    if not api_key or not api_key.strip():
        raise GeminiError(503, "analysis_unconfigured", "Gemini API 키를 입력해 주세요.")
    config = {"maxOutputTokens": 8192}
    if thinking_level := THINKING_LEVEL_BY_MODEL.get(model):
        config["thinkingConfig"] = {"thinkingLevel": thinking_level}
    elif model in {"gemini-2.5-flash", "gemini-2.5-flash-lite"}:
        config["thinkingConfig"] = {"thinkingBudget": 0}
    try:
        async with asyncio.timeout(25), httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta/",
            timeout=httpx.Timeout(20, connect=5), transport=transport,
        ) as client:
            response = await client.post(
                f"models/{model}:generateContent",
                headers={"x-goog-api-key": api_key.strip()},
                json={"contents": [{"parts": [{"text": "Reply with OK only."}]}],
                      "generationConfig": config},
            )
            response.raise_for_status()
            candidates = response.json().get("candidates", [])
            if not candidates or candidates[0].get("finishReason") != "STOP" or not any(
                part.get("text", "").strip() for part in candidates[0].get("content", {}).get("parts", [])
                if not part.get("thought", False)
            ):
                raise GeminiError(502, "analysis_probe_failed", "Gemini 연결은 됐지만 응답을 생성하지 못했어요.")
    except httpx.HTTPStatusError as error:
        described = describe_http_error(error.response)
        described.provider_status = error.response.status_code
        try:
            body = error.response.json().get("error", {})
            message = str(body.get("message", "")).casefold()
            described.diagnostic = next((name for name, fragment in {
                "thinking_setting": "thinking", "output_limit": "output",
                "invalid_key": "api key", "billing": "billing", "region": "location",
                "model": "model", "quota": "quota", "payload": "payload",
            }.items() if fragment in message), "unknown")
        except (AttributeError, ValueError):
            described.diagnostic = "unknown"
        raise described from None
    except (TimeoutError, httpx.TimeoutException):
        raise GeminiError(504, "analysis_connection_timeout", "사진 없이 보낸 연결 확인 요청도 시간 초과됐어요. Gemini 서비스 또는 네트워크 연결을 확인해 주세요.") from None
    except (httpx.RequestError, ValueError, AttributeError, TypeError):
        raise GeminiError(502, "analysis_connection_failed", "Gemini에 연결하지 못했어요. 인터넷 연결을 확인해 주세요.") from None

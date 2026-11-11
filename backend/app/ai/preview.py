import httpx
from fastapi import FastAPI, HTTPException, Query, Request

from .connection import check_connection
from .gemini import GeminiError, describe_http_error
from .router import get_analyzer, router

app = FastAPI(title="WashWise AI 사진 분석")
app.include_router(router)


@app.get("/api/available-models", tags=["preview"])
async def available_models(request: Request):
    """List usable text/image analysis models for local configuration."""
    analyzer = get_analyzer(request)
    if not analyzer.api_key:
        raise HTTPException(503, detail={"code": "analysis_unconfigured"})
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                        headers={"x-goog-api-key": analyzer.api_key})
            response.raise_for_status()
            return {"configured_model": analyzer.model, "models": [
                model["name"] for model in response.json().get("models", [])
                if "generateContent" in model.get("supportedGenerationMethods", [])
            ]}
    except httpx.HTTPStatusError as error:
        described = describe_http_error(error.response)
        raise HTTPException(described.status_code, detail={"code": described.code, "message": str(described)}) from None
    except (httpx.RequestError, ValueError):
        raise HTTPException(502, detail={"code": "model_list_unavailable", "message": "모델 목록을 가져오지 못했어요."}) from None


@app.post("/api/check-connection", tags=["preview"])
async def preview_connection(request: Request, model: str | None = Query(default=None, pattern=r"^gemini-[a-z0-9.-]+$")):
    """Check actual Gemini generation without uploading a photo (preview only)."""
    analyzer = get_analyzer(request)
    model = model or analyzer.model
    try:
        await check_connection(analyzer.api_key, model)
    except GeminiError as error:
        raise HTTPException(error.status_code, detail={
            "code": error.code, "message": str(error), "model": model,
            "provider_status": getattr(error, "provider_status", None),
            "diagnostic": getattr(error, "diagnostic", None),
        }) from None
    return {"status": "ready", "model": model}

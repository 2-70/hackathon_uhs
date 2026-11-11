"""Serve the Expo web export and the full WashWise API from one local address."""

import os
import re
from pathlib import Path

import httpx
from fastapi import Request, Response
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from backend.app.main import app

catalog_api_url = os.getenv("WASHWISE_CATALOG_API_URL", "").rstrip("/")


if catalog_api_url:
    @app.middleware("http")
    async def forward_catalog(request: Request, call_next):
        path = request.url.path
        if request.method != "GET" or not re.fullmatch(
            r"/api/catalog/(?:stats|models(?:/[0-9a-fA-F-]{36}/usage)?)", path
        ):
            return await call_next(request)
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                result = await client.get(f"{catalog_api_url}{path}", params=request.query_params)
        except httpx.RequestError:
            return Response(
                '{"error":{"message":"세탁기 카탈로그에 연결하지 못했어요."}}',
                status_code=502,
                media_type="application/json",
            )
        return Response(result.content, status_code=result.status_code, media_type="application/json")


class AppFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            # Direct visits to Expo routes use the same entry point as in-app navigation.
            target = Path(path)
            if error.status_code != 404 or target.parts[:1] == ("api",) or target.suffix:
                raise
            return await super().get_response("index.html", scope)


app.mount("/", AppFiles(directory=os.environ["WASHWISE_WEB_BUILD_DIR"], html=True), name="washwise-web")

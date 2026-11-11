import logging
import re
from asyncio import gather, timeout
from collections.abc import Sequence
from io import BytesIO
from urllib.parse import unquote

import httpx
from PIL import Image, ImageOps
from pydantic import HttpUrl, ValidationError
from starlette.concurrency import run_in_threadpool

from .schemas import ProductCandidate
from .web_search import WebSearchUnavailable

IMAGE_UPLOAD_LIMIT = 500_000
SERPAPI_HOST = "serpapi.com"


def prepare_lens_image(data: bytes) -> bytes:
    with (
        Image.open(BytesIO(data)) as original,
        ImageOps.exif_transpose(original).convert("RGB") as photo,
    ):
        for max_edge in (1600, 1200, 900, 640):
            photo.thumbnail((max_edge, max_edge))
            with BytesIO() as jpeg:
                photo.save(jpeg, format="JPEG", quality=85, optimize=True)
                if jpeg.tell() <= IMAGE_UPLOAD_LIMIT:
                    return jpeg.getvalue()
    raise WebSearchUnavailable


def redact_lens_search_url(record: logging.LogRecord) -> bool:
    # HTTPX logs request URLs at INFO. SerpApi requires the search key in the query string.
    args = record.args
    if isinstance(args, tuple) and len(args) > 1:
        url = args[1]
        if isinstance(url, httpx.URL) and url.host == SERPAPI_HOST and url.path == "/search.json":
            record.args = (args[0], url.copy_with(query=None), *args[2:])
    return True


class LensCandidate(ProductCandidate):
    image_url: HttpUrl | None = None
    thumbnail_url: HttpUrl | None = None
    exact_match: bool = False


def candidate_product_codes(candidates: Sequence[LensCandidate], brand: str = "") -> list[str]:
    codes = []
    for candidate in candidates[:8]:
        clues = f"{candidate.name} {unquote(candidate.source_url.path or '')}"
        codes.extend(re.findall(r"\b[A-Z]{1,5}[0-9]{3,8}-[A-Z0-9]{2,6}\b", clues.upper()))
        if brand == "puma" or re.search(r"\bPUMA\b|푸마", candidate.name, re.IGNORECASE):
            # Ignore numeric retailer item IDs in the URL.
            codes.extend(re.findall(r"(?<!\d)\d{6}[-_ ]?\d{2}(?!\d)", candidate.name))
        if brand == "adidas" or re.search(r"\bADIDAS\b|아디다스", candidate.name, re.IGNORECASE):
            codes.extend(re.findall(r"\b[A-Z]{2}\d{4,6}\b", clues.upper()))
        if brand == "uniqlo" or re.search(r"\bUNIQLO\b|유니클로", candidate.name, re.IGNORECASE):
            codes.extend(re.findall(r"\bE\d{6}(?:-\d{3})?\b", clues.upper()))
    return list(dict.fromkeys(codes))


def parse_candidates(matches: list, *, exact_match: bool = False) -> list[LensCandidate]:
    candidates: dict[str, LensCandidate] = {}
    for match in matches:
        if not isinstance(match, dict) or not isinstance(match.get("title"), str):
            continue
        name = match["title"].strip()[:300]
        if not name:
            continue
        try:
            candidate = LensCandidate.model_validate({
                "name": name, "source_url": match.get("link"), "exact_match": exact_match,
            })
        except ValidationError:
            continue
        url = candidate.source_url
        if url.scheme != "https" or url.username is not None or url.password is not None:
            continue
        for field in ("image", "thumbnail"):
            try:
                candidate.image_url = HttpUrl(match[field])
                break
            except (KeyError, TypeError, ValueError):
                continue
        try:
            candidate.thumbnail_url = HttpUrl(match["thumbnail"])
        except (KeyError, TypeError, ValueError):
            pass
        candidates.setdefault(str(url), candidate)
        if len(candidates) == 15:
            break
    return list(candidates.values())


class LensWebSearch:
    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = api_key
        self.transport = transport
        logging.getLogger("httpx").addFilter(redact_lens_search_url)

    async def search_product_pages(self, query: str) -> list[HttpUrl]:
        async with httpx.AsyncClient(
            base_url=f"https://{SERPAPI_HOST}", transport=self.transport,
        ) as client:
            matches = await self.search_results(client, {
                "api_key": self.api_key, "engine": "google", "q": query, "hl": "en",
            }, "organic_results")
        if matches is None:
            raise WebSearchUnavailable
        return [candidate.source_url for candidate in parse_candidates(matches)]

    async def search(self, image: bytes, hint: str | None = None) -> list[LensCandidate]:
        try:
            async with timeout(20):
                jpeg = await run_in_threadpool(prepare_lens_image, image)
                async with httpx.AsyncClient(
                    base_url=f"https://{SERPAPI_HOST}",
                    timeout=httpx.Timeout(20, connect=3),
                    transport=self.transport,
                ) as client:
                    upload = await client.post(
                        "/image",
                        data={"api_key": self.api_key},
                        files={"image": ("garment.jpg", jpeg, "image/jpeg")},
                        timeout=httpx.Timeout(7, connect=3),
                    )
                    upload.raise_for_status()
                    uploaded = upload.json()
                    image_id = uploaded.get("image_id")
                    if uploaded.get("error") or not isinstance(image_id, str) or not image_id.strip():
                        raise WebSearchUnavailable
                    visual, exact = await gather(
                        self.search_matches(client, image_id, "visual_matches", hint),
                        self.search_matches(client, image_id, "exact_matches"),
                    )
            if visual is None and exact is None:
                raise WebSearchUnavailable
            candidates = {str(item.source_url): item for item in parse_candidates(exact or [], exact_match=True)}
            for item in parse_candidates(visual or []):
                url = str(item.source_url)
                if url in candidates:
                    item.exact_match = True
                    item.image_url = item.image_url or candidates[url].image_url
                    item.thumbnail_url = item.thumbnail_url or candidates[url].thumbnail_url
                candidates[url] = item
            return list(candidates.values())
        except (httpx.HTTPError, OSError, AttributeError, ValueError):
            raise WebSearchUnavailable from None

    async def search_matches(
        self, client: httpx.AsyncClient, image_id: str, search_type: str, hint: str | None = None,
    ) -> list | None:
        params = {
            "api_key": self.api_key, "engine": "google_lens", "image_id": image_id,
            "type": search_type, "hl": "ko", "country": "kr",
        }
        if search_type == "visual_matches":
            params["auto_crop"] = "true"
            if hint:
                params["q"] = hint
        return await self.search_results(client, params, search_type)

    async def search_results(
        self, client: httpx.AsyncClient, params: dict[str, str], result_field: str,
    ) -> list | None:
        try:
            response = await client.get("/search.json", params=params, timeout=httpx.Timeout(12, connect=3))
            response.raise_for_status()
            results = response.json()
            status = results.get("search_metadata", {}).get("status")
            matches = results.get(result_field, [])
            if status not in (None, "Success") or (status is None and results.get("error")):
                return None
            return matches if isinstance(matches, list) else None
        except (httpx.HTTPError, AttributeError, ValueError):
            return None

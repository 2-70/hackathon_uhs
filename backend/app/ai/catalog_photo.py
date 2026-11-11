import base64
from collections.abc import Sequence
from hashlib import sha256

import httpx
from starlette.concurrency import run_in_threadpool

from .catalog import (
    CatalogProduct,
    brand_key,
    official_url_key,
    product_code_key,
    visible_product_code,
)
from .lens import LensCandidate, candidate_product_codes, prepare_lens_image
from .schemas import GarmentReadings
from .web_search import WebSearchUnavailable

REFERENCE_IMAGE_HOSTS = {"static.nike.com", "img.29cm.co.kr"}
MAX_REFERENCE_BYTES = 5_000_000


def catalog_photo_candidates(
    garment: GarmentReadings, candidates: Sequence[LensCandidate], entries: Sequence[CatalogProduct],
) -> list[CatalogProduct]:
    brand = brand_key(garment.brand.value) if garment.brand else ""
    code_in_photo = visible_product_code(garment)
    codes = {product_code_key(code) for code in candidate_product_codes(candidates, brand)}
    links = {key for candidate in candidates if (key := official_url_key(candidate.source_url))}
    return [
        entry for entry in entries
        if entry.reference_image_url is not None
        and (not brand or brand == brand_key(entry.product.brand))
        and (not code_in_photo or code_in_photo == product_code_key(entry.product.product_code))
        and (
            product_code_key(entry.product.product_code) in codes
            or official_url_key(entry.product.source_url) in links
            or official_url_key(entry.reference_page_url) in links
        )
    ][:3]


async def read_reference_image(client: httpx.AsyncClient, entry: CatalogProduct) -> bytes | None:
    url = entry.reference_image_url
    if url is None or url.host not in REFERENCE_IMAGE_HOSTS or official_url_key(url) is None:
        return None
    try:
        async with client.stream("GET", str(url)) as response:
            response.raise_for_status()
            if not response.headers.get("content-type", "").startswith("image/"):
                return None
            image = bytearray()
            async for chunk in response.aiter_bytes():
                if len(image) + len(chunk) > MAX_REFERENCE_BYTES:
                    return None
                image.extend(chunk)
        if entry.image_sha256 and sha256(image).hexdigest() not in entry.image_sha256:
            return None
        return await run_in_threadpool(prepare_lens_image, bytes(image))
    except (httpx.HTTPError, OSError, ValueError, WebSearchUnavailable):
        return None


def image_part(image: bytes, mime_type: str) -> dict:
    return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(image).decode("ascii")}}

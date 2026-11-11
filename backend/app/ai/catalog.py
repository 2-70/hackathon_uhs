import re
from collections.abc import Sequence
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from unicodedata import normalize
from urllib.parse import parse_qsl

from pydantic import BaseModel, HttpUrl, StringConstraints, TypeAdapter, ValidationError

from .analysis import describe_care, format_fields, request_label_photo
from .schemas import (
    AnalysisResponse,
    AnalyzedField,
    GarmentReadings,
    LabelReadings,
    ProductCandidate,
    ProductCareResponse,
    ProductInfo,
    ProductLookup,
    ProductMatchRequest,
)

CATALOG_PATH = Path(__file__).resolve().parents[2] / "seed" / "verified" / "products.json"
MatchMethod = Literal["reference_photo", "product_code", "official_url", "web_image"]
BRAND_ALIASES = {"나이키": "nike", "쿠어": "coor"}
TRACKING_PARAMETERS = {"gclid", "fbclid", "msclkid"}


class CatalogProduct(BaseModel):
    product: ProductInfo
    garment_type: str
    image_sha256: list[Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]]
    reference_image_url: HttpUrl | None = None
    reference_page_url: HttpUrl | None = None
    care: LabelReadings


@lru_cache(maxsize=1)
def load_catalog() -> list[CatalogProduct]:
    return TypeAdapter(list[CatalogProduct]).validate_json(CATALOG_PATH.read_bytes())


def get_catalog() -> Sequence[CatalogProduct] | None:
    """Preview provider. A database-backed dependency can return the same records."""
    try:
        return load_catalog()
    except (OSError, ValidationError):
        return None


def match_reference_photo(image: bytes, entries: Sequence[CatalogProduct]) -> CatalogProduct | None:
    digest = sha256(image).hexdigest()
    matches = [entry for entry in entries if digest in entry.image_sha256]
    return matches[0] if len(matches) == 1 else None


def search_key(value: str | None) -> str:
    return normalize("NFKC", value or "").strip().casefold()


def brand_key(value: str | None) -> str:
    key = search_key(value)
    return BRAND_ALIASES.get(key, key)


def garment_key(value: str | None) -> str:
    key = "".join(search_key(value).split())
    if any(term in key for term in ("후드", "후디", "hoodie")):
        return "hoodie"
    if any(term in key for term in ("맨투맨", "스웨트셔츠", "스웻셔츠", "sweatshirt")):
        return "sweatshirt"
    return key


def official_url_key(url: HttpUrl | None) -> tuple[str | None, str, tuple[tuple[str, str], ...]] | None:
    if url is None or url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
        return None
    query = tuple(sorted(
        (name, value) for name, value in parse_qsl(url.query or "", keep_blank_values=True)
        if not name.casefold().startswith("utm_") and name.casefold() not in TRACKING_PARAMETERS
    ))
    return url.host, (url.path or "/").rstrip("/"), query


def products_with_code(brand: str, code: str, entries: Sequence[CatalogProduct]) -> list[CatalogProduct]:
    if not brand or not code:
        return []
    return [
        entry for entry in entries
        if brand_key(entry.product.brand) == brand and search_key(entry.product.product_code) == code
    ]


def match_photo_product_code(garment: GarmentReadings, entries: Sequence[CatalogProduct]) -> CatalogProduct | None:
    code = garment.product_code
    if not garment.brand or not code:
        return None
    if not re.search(
        rf"(?<![a-z0-9-]){re.escape(search_key(code.value))}(?![a-z0-9-])",
        search_key(code.evidence),
    ):
        return None
    matches = products_with_code(brand_key(garment.brand.value), search_key(code.value), entries)
    return matches[0] if len(matches) == 1 else None


def match_catalog(
    clues: ProductMatchRequest, entries: Sequence[CatalogProduct],
) -> tuple[ProductLookup, CatalogProduct | None]:
    brand = brand_key(clues.brand)
    code = search_key(clues.product_code)
    url = official_url_key(clues.source_url)
    by_code = products_with_code(brand, code, entries)
    by_url = [entry for entry in entries if url is not None and official_url_key(entry.product.source_url) == url]
    if clues.source_url is not None:
        exact = [
            entry for entry in by_url
            if (not brand or brand_key(entry.product.brand) == brand)
            and (not code or search_key(entry.product.product_code) == code)
        ]
        method = "official_url"
    else:
        exact = by_code
        method = "product_code"
    if len(exact) == 1:
        return ProductLookup(status="matched", match_method=method, product=exact[0].product), exact[0]

    kind = garment_key(clues.garment_type)
    similar = [
        entry for entry in entries
        if kind and garment_key(entry.garment_type) == kind
        and (not brand or brand_key(entry.product.brand) == brand)
    ]
    color = search_key(clues.color)
    if color:
        similar.sort(key=lambda entry: color in search_key(entry.product.color), reverse=True)
    candidates = {
        entry.product.id: ProductCandidate(name=entry.product.name, source_url=entry.product.source_url)
        for entry in [*by_code, *by_url, *similar]
    }
    return ProductLookup(
        status="candidates" if candidates else "not_found", candidates=list(candidates.values())[:5],
    ), None


def match_web_image(full_image_urls: list[HttpUrl], entries: Sequence[CatalogProduct]) -> CatalogProduct | None:
    # The source CDN can serve the same photo in multiple sizes and formats.
    image_locations = {(url.host, url.path) for url in full_image_urls if url.scheme == "https"}
    matches = [
        entry for entry in entries
        if entry.reference_image_url is not None
        and (entry.reference_image_url.host, entry.reference_image_url.path) in image_locations
    ]
    return matches[0] if len(matches) == 1 else None


def describe_product_care(entry: CatalogProduct) -> ProductCareResponse:
    guidance = describe_care(entry.care, official_product=True)
    photo_request = request_label_photo(entry.care)
    return ProductCareResponse(
        product=entry.product,
        product_care=format_fields(entry.care, source="official_product"),
        care_guidance=guidance,
        care_guidance_source="official_product" if guidance else None,
        photo_request=photo_request,
        next_actions=["capture_label", "manual_entry"] if photo_request else [],
        message=(
            f"상품을 확인했어요. {photo_request.instructions}"
            if photo_request else "상품 공식 안내에서 세탁·건조 방법을 찾았어요."
        ),
    )


def attach_product(
    entry: CatalogProduct, method: MatchMethod, result: AnalysisResponse | None = None
) -> AnalysisResponse:
    product = entry.product
    garment = dict(result.garment) if result else format_fields(GarmentReadings())
    for key, value in (
        ("garment_type", entry.garment_type),
        ("brand", product.brand),
        ("color", product.color),
        ("product_name", product.name),
        ("product_code", product.product_code),
    ):
        if value is not None:
            garment[key] = AnalyzedField(
                value=value, source="official_product", status="verified", evidence=product.name,
            )

    care = describe_product_care(entry)
    estimated_guidance = result.care_guidance if result and result.care_guidance_source == "estimated" else []
    return AnalysisResponse(
        image_type="garment",
        status="analyzed",
        garment=garment,
        product_lookup=ProductLookup(status="matched", match_method=method, product=product),
        product_care=care.product_care,
        care_guidance=care.care_guidance or estimated_guidance,
        care_guidance_source=care.care_guidance_source or ("estimated" if estimated_guidance else None),
        photo_request=care.photo_request,
        next_actions=care.next_actions,
        message=care.message,
    )

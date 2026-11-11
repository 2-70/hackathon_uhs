import re
from collections.abc import Sequence
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from unicodedata import normalize
from urllib.parse import parse_qsl

from pydantic import BaseModel, HttpUrl, StringConstraints, TypeAdapter, ValidationError

from .analysis import (
    describe_care,
    format_fields,
    is_padded_garment,
    material_guidance,
    new_label_photo_request,
    request_label_photo,
)
from .schemas import (
    AnalysisResponse,
    AnalyzedField,
    GarmentReadings,
    LabelReadings,
    MaterialCareTips,
    ProductCandidate,
    ProductCareResponse,
    ProductGuidanceSource,
    ProductInfo,
    ProductLookup,
    ProductMatchRequest,
    ProductSource,
)

CATALOG_PATH = Path(__file__).resolve().parents[2] / "seed" / "verified" / "products.json"
MatchMethod = Literal["reference_photo", "product_code", "official_url", "web_image"]
BRAND_ALIASES = {
    "나이키": "nike", "쿠어": "coor", "아디다스": "adidas", "유니클로": "uniqlo",
    "뉴발란스": "new balance", "푸마": "puma", "자라": "zara", "노스페이스": "the north face",
    "무인양품": "muji", "파타고니아": "patagonia", "리바이스": "levi's", "갭": "gap",
    "조던": "nike", "에어 조던": "nike", "jordan": "nike", "air jordan": "nike",
    "아디다스 오리지널스": "adidas", "adidas originals": "adidas", "uniqlo u": "uniqlo",
    "오프화이트": "off-white", "스투시": "stussy", "칼하트": "carhartt", "폴로": "polo", "라코스테": "lacoste",
    "타미힐피거": "tommy hilfiger", "챔피온": "champion", "언더아머": "under armour", "아크테릭스": "arc'teryx",
    "컬럼비아": "columbia", "휠라": "fila", "리복": "reebok", "컨버스": "converse", "반스": "vans",
    "에이치앤엠": "h&m", "무신사 스탠다드": "musinsa standard", "스파오": "spao", "탑텐": "topten",
}
TRACKING_PARAMETERS = {"gclid", "fbclid", "msclkid", "srsltid"}


class CatalogProduct(BaseModel):
    product: ProductInfo
    garment_type: str
    image_sha256: list[Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]]
    reference_image_url: HttpUrl | None = None
    reference_page_url: HttpUrl | None = None
    care_source: ProductSource = "official_product"
    care: LabelReadings
    material_tips: MaterialCareTips | None = None


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


def same_brand(first: str | None, second: str | None) -> bool:
    """Match a brand written with its translation, such as "나이키(NIKE)" and "Nike"."""
    names = []
    for value in (first, second):
        key = search_key(value)
        parts = [part.strip() for part in re.split(r"[()\[\]/,|·]", key)]
        # Compare without spacing and punctuation, so "OFF WHITE" equals "Off-White".
        names.append({re.sub(r"[^0-9a-z가-힣]", "", brand_key(part)) for part in (key, *parts) if part} - {""})
    if names[0] & names[1]:
        return True
    # A sub-line or a longer legal name still names the brand ("Nike Sportswear", "Off-White c/o Virgil Abloh").
    return any(
        len(short) >= 4 and short in long
        for one in names[0] for other in names[1]
        for short, long in ((one, other), (other, one))
    )


def product_code_key(value: str | None) -> str:
    key = search_key(value)
    if re.fullmatch(r"[0-9]{6}[-_ ]?[0-9]{2}", key):
        return re.sub(r"[-_ ]", "", key)
    return key


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
        if brand_key(entry.product.brand) == brand and product_code_key(entry.product.product_code) == code
    ]


def match_photo_product_code(garment: GarmentReadings, entries: Sequence[CatalogProduct]) -> CatalogProduct | None:
    code = visible_product_code(garment)
    if not garment.brand or code is None:
        return None
    matches = products_with_code(brand_key(garment.brand.value), code, entries)
    return matches[0] if len(matches) == 1 else None


def visible_product_code(garment: GarmentReadings) -> str | None:
    code = garment.product_code
    if code is None:
        return None
    key = search_key(code.value)
    if not re.search(
        rf"(?<![a-z0-9-]){re.escape(key)}(?![a-z0-9-])",
        search_key(code.evidence),
    ):
        return None
    return product_code_key(key)


def match_catalog(
    clues: ProductMatchRequest, entries: Sequence[CatalogProduct],
) -> tuple[ProductLookup, CatalogProduct | None]:
    brand = brand_key(clues.brand)
    code = product_code_key(clues.product_code)
    url = official_url_key(clues.source_url)
    by_code = products_with_code(brand, code, entries)
    by_url = [entry for entry in entries if url is not None and official_url_key(entry.product.source_url) == url]
    if clues.source_url is not None:
        exact = [
            entry for entry in by_url
            if (not brand or brand_key(entry.product.brand) == brand)
            and (not code or product_code_key(entry.product.product_code) == code)
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


def describe_product_care(entry: CatalogProduct, *, observed_type: str = "") -> ProductCareResponse:
    fiber_content = entry.care.fiber_content.value if entry.care.fiber_content else ""
    padded = is_padded_garment(f"{entry.garment_type} {entry.product.name} {observed_type}", fiber_content)
    published = describe_care(entry.care, product_source=entry.care_source)
    by_material = material_guidance(
        entry.care,
        entry.material_tips,
        padded=padded,
        garment_description=f"{entry.garment_type} {entry.product.name} {observed_type}",
    )
    guidance = [*published, *by_material]
    photo_request = new_label_photo_request(padded=True) if padded and entry.care.wash_method is None else request_label_photo(entry.care)
    if by_material and photo_request is None:
        photo_request = new_label_photo_request(padded=padded)
    source = "판매처 상품 안내" if entry.care_source == "product_listing" else "상품 공식 안내"
    guidance_source: ProductGuidanceSource | None = None
    if published and by_material:
        guidance_source = entry.care_source
        message = f"{source}에서 확인한 항목과 소재 기준의 잠정 권장 사항을 구분해 표시했어요."
    elif by_material:
        guidance_source = "material_estimate"
        message = "상품 페이지에서 확인한 소재 정보에 따른 잠정 관리 권장 사항이에요. 정확한 세탁법은 실제 옷의 라벨을 확인해 주세요."
    elif published:
        guidance_source = entry.care_source
        message = f"{source}에서 확인한 관리 방법이에요."
    else:
        guidance_source = None
        if entry.care.fiber_content:
            message = "상품 페이지에서 소재 정보는 확인했지만, 그 정보만으로 세탁 정보를 확실하게 판단할 수 없어요. 실제 옷의 세탁 라벨을 찍어 주세요."
        else:
            message = "같은 상품을 찾았지만 상품 페이지에서 세탁 안내와 소재 정보를 확인하지 못해 세탁 정보를 확실하게 알 수 없어요. 실제 옷의 세탁 라벨을 찍어 주세요."
    if photo_request:
        message = f"{message} {photo_request.instructions}"
    return ProductCareResponse(
        product=entry.product,
        product_care=format_fields(entry.care, source=entry.care_source),
        care_guidance=guidance,
        care_guidance_source=guidance_source,
        photo_request=photo_request,
        next_actions=["capture_label", "manual_entry"] if photo_request else [],
        message=message,
    )


def attach_product(
    entry: CatalogProduct, method: MatchMethod, result: AnalysisResponse | None = None
) -> AnalysisResponse:
    product = entry.product
    garment = dict(result.garment) if result else format_fields(GarmentReadings())
    observed_type = garment.get("garment_type")
    for key, value in (
        ("garment_type", entry.garment_type),
        ("brand", product.brand),
        ("color", product.color),
        ("product_name", product.name),
        ("product_code", product.product_code),
    ):
        if value:
            garment[key] = AnalyzedField(
                value=value, source=entry.care_source, status="verified", evidence=product.name,
            )

    seen_type = str(observed_type.value or "") if observed_type else ""
    care = describe_product_care(entry, observed_type=seen_type)
    return AnalysisResponse(
        image_type="garment",
        status="analyzed",
        garment=garment,
        product_lookup=ProductLookup(status="matched", match_method=method, product=product),
        product_care=care.product_care,
        care_guidance=care.care_guidance,
        care_guidance_source=care.care_guidance_source,
        photo_request=care.photo_request,
        next_actions=care.next_actions,
        message=care.message,
    )

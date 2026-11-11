import os
from collections import OrderedDict
from collections.abc import Sequence
from contextlib import asynccontextmanager
from hashlib import sha256
from io import BytesIO
from time import monotonic
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

from .analysis import (
    format_analysis,
    home_wash_unsuitable,
    request_care_label_for_unmatched_product,
)
from .catalog import (
    CatalogProduct,
    attach_product,
    describe_product_care,
    get_catalog,
    match_catalog,
    match_photo_product_code,
    match_reference_photo,
    match_web_image,
)
from .gemini import (
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    GeminiAnalyzer,
    GeminiError,
    configured_gemini_keys,
    create_gemini_client,
)
from .lens import LensWebSearch
from .official_product import (
    OfficialLookupUnavailable,
    confirm_product,
    read_photo_and_product,
)
from .schemas import (
    AnalysisResponse,
    GarmentReadings,
    GarmentSearchStage,
    PhotoReadings,
    ProductCareResponse,
    ProductLookup,
    ProductMatchRequest,
    RequestedPhotoType,
)
from .web_search import VisionWebSearch, WebSearchUnavailable

PhotoCacheKey = tuple[str, RequestedPhotoType, bytes]


class PhotoReadingsCache:
    def __init__(self) -> None:
        self.entries: OrderedDict[PhotoCacheKey, tuple[float, PhotoReadings]] = OrderedDict()

    def get(self, key: PhotoCacheKey) -> PhotoReadings | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        expires_at, readings = entry
        if expires_at <= monotonic():
            del self.entries[key]
            return None
        self.entries.move_to_end(key)
        return readings

    def put(self, key: PhotoCacheKey, readings: PhotoReadings) -> None:
        self.entries[key] = (monotonic() + 300, readings)
        self.entries.move_to_end(key)
        if len(self.entries) > 64:
            self.entries.popitem(last=False)


@asynccontextmanager
async def ai_lifespan(_: FastAPI):
    async with create_gemini_client() as client:
        yield {"washwise_gemini_client": client, "washwise_photo_cache": PhotoReadingsCache()}


router = APIRouter(prefix="/api", tags=["ai"], lifespan=ai_lifespan)
Catalog = Annotated[Sequence[CatalogProduct] | None, Depends(get_catalog)]
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_INLINE_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 32_000_000
MAX_COMPRESSED_IMAGE_EDGE = 3072
MAX_AUTO_OR_GARMENT_EDGE = 2560
IMAGE_MIME_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def get_analyzer(request: Request) -> GeminiAnalyzer:
    model = os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
    keys = configured_gemini_keys()
    return GeminiAnalyzer(
        api_key=keys[0] if keys else None,
        backup_keys=keys[1:],
        model=model,
        client=getattr(request.state, "washwise_gemini_client", None),
        fallback_model=FALLBACK_MODEL if model == DEFAULT_MODEL else None,
    )


def get_web_search() -> VisionWebSearch | None:
    api_key = os.getenv("GOOGLE_CLOUD_VISION_API_KEY")
    return VisionWebSearch(api_key) if api_key else None


def get_lens_search() -> LensWebSearch | None:
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    return LensWebSearch(api_key) if api_key else None


@router.post("/products/match", response_model=ProductLookup, responses={503: {"model": ProductLookup}})
def search_products(clues: ProductMatchRequest, response: Response, entries: Catalog) -> ProductLookup:
    if entries is None:
        response.status_code = 503
        return ProductLookup(status="search_unavailable")
    lookup, _ = match_catalog(clues, entries)
    return lookup


@router.get("/products/{product_id}/care", response_model=ProductCareResponse)
def get_product_care(product_id: str, entries: Catalog) -> ProductCareResponse:
    if entries is None:
        raise HTTPException(503, detail={"code": "search_unavailable", "message": "상품 정보를 조회하지 못했어요."})
    entry = next((item for item in entries if item.product.id == product_id), None)
    if entry is None:
        raise HTTPException(404, detail={"code": "product_not_found", "message": "등록된 상품을 찾지 못했어요."})
    return describe_product_care(entry)


def prepare_image(data: bytes, image_type: RequestedPhotoType = "auto") -> tuple[bytes, str]:
    max_edge = MAX_COMPRESSED_IMAGE_EDGE
    if image_type != "care_label":
        max_edge = min(max_edge, MAX_AUTO_OR_GARMENT_EDGE)
    try:
        with Image.open(BytesIO(data)) as image:
            is_mpo = image.format == "MPO"
            mime_type = IMAGE_MIME_TYPES["JPEG"] if is_mpo else IMAGE_MIME_TYPES.get(image.format)
            if mime_type is None or (not is_mpo and getattr(image, "is_animated", False)):
                raise HTTPException(
                    415, detail={"code": "unsupported_image", "message": "JPEG, PNG, WebP 사진을 올려 주세요."}
                )
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise Image.DecompressionBombError("Image exceeds the supported resolution")

            needs_compression = (
                len(data) > MAX_INLINE_IMAGE_BYTES
                or max(image.size) > max_edge
            )
            if is_mpo or needs_compression:
                return prepare_jpeg(image, max_edge=max_edge), IMAGE_MIME_TYPES["JPEG"]

            image.load()
            return data, mime_type
    except Image.DecompressionBombError:
        raise HTTPException(
            413, detail={"code": "image_too_large", "message": "해상도가 더 작은 사진을 올려 주세요."}
        ) from None
    except (OSError, SyntaxError, ValueError):
        raise HTTPException(
            422, detail={"code": "invalid_image", "message": "사진을 열 수 없어요. 다시 올려 주세요."}
        ) from None


def prepare_jpeg(image: Image.Image, *, max_edge: int) -> bytes:
    # Pillow opens the primary photo first in an MPO file.
    image.thumbnail((max_edge, max_edge))
    # A square bounding box is unchanged by rotation. Transpose fewer pixels.
    ImageOps.exif_transpose(image, in_place=True)
    if "A" in image.getbands() or "transparency" in image.info:
        with image.convert("RGBA") as rgba:
            background = Image.new("RGB", image.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    elif image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    with BytesIO() as jpeg:
        image.save(jpeg, format="JPEG", quality=90)
        if jpeg.tell() > MAX_INLINE_IMAGE_BYTES:
            raise HTTPException(
                413, detail={"code": "image_too_large", "message": "용량이 더 작은 사진을 올려 주세요."}
            )
        return jpeg.getvalue()


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_photo(
    request: Request,
    image: Annotated[UploadFile, File(description="의류 또는 세탁 라벨 사진")],
    analyzer: Annotated[GeminiAnalyzer, Depends(get_analyzer)],
    web_search: Annotated[VisionWebSearch | None, Depends(get_web_search)],
    lens_search: Annotated[LensWebSearch | None, Depends(get_lens_search)],
    entries: Catalog,
    image_type: Annotated[RequestedPhotoType, Form(description="사진의 종류")] = "auto",
    search_stage: Annotated[GarmentSearchStage, Form(description="의류 검색 단계")] = "initial",
) -> AnalysisResponse:
    try:
        # Avoid loading oversized uploads from the temporary file into memory.
        data = None
        if image.size is None or image.size <= MAX_UPLOAD_BYTES:
            data = await image.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await image.close()
    if data is None or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, detail={"code": "image_too_large", "message": "40MB 이하의 사진을 올려 주세요."}
        )

    prepared_image, mime_type = await run_in_threadpool(prepare_image, data, image_type)
    cache: PhotoReadingsCache | None = getattr(request.state, "washwise_photo_cache", None)
    cache_key = (analyzer.model, image_type, sha256(data).digest())
    cached_readings = cache.get(cache_key) if cache is not None else None
    readings = cached_readings
    # A garment photo is searched first, so one model request can read the photo and identify the product.
    single_request = (
        lens_search is not None and image_type != "care_label" and search_stage != "estimate" and bool(analyzer.api_key)
    )
    candidates, combined, search_failed, lookup_warning = [], None, False, None
    if single_request:
        if entries and (entry := match_reference_photo(data, entries)):
            return attach_product(entry, "reference_photo")
        try:
            candidates = await lens_search.search(prepared_image)
        except WebSearchUnavailable:
            search_failed = True
        if candidates:
            try:
                combined = await read_photo_and_product(
                    analyzer, prepared_image, mime_type, image_type, candidates, entries or (), lens_search,
                )
            except OfficialLookupUnavailable as error:
                # The photo alone is read below, so the user still gets the garment and a label request.
                lookup_warning = str(error)
        if combined:
            readings = combined[0]
    if readings is None:
        try:
            readings = await analyzer.analyze(prepared_image, mime_type, image_type)
        except GeminiError as error:
            if entries and image_type != "care_label" and (entry := match_reference_photo(data, entries)):
                return attach_product(entry, "reference_photo")
            raise HTTPException(
                error.status_code, detail={"code": error.code, "message": str(error)}
            ) from None
    result = format_analysis(readings, image_type)
    if cache is not None and cached_readings is None:
        label_read = result.image_type == "care_label" and result.status == "analyzed"
        garment = readings.garment
        garment_read = result.image_type == "garment" and garment and garment.garment_type and garment.color
        if label_read or garment_read:
            cache.put(cache_key, readings)
    if result.image_type != "garment":
        return result

    garment = readings.garment or GarmentReadings()
    if entries:
        if entry := match_reference_photo(data, entries):
            return attach_product(entry, "reference_photo", result)
        coded_product = match_photo_product_code(garment, entries)
        if coded_product:
            return attach_product(coded_product, "product_code", result)
    if search_stage == "estimate":
        return result
    kind = " ".join(field.value for field in (garment.garment_type, garment.product_name) if field)
    if home_wash_unsuitable(kind):
        # The kind of garment is judged first. One that is not washed at home needs no product search.
        label = garment.garment_type.value if garment.garment_type else "이 옷"
        result.message = (
            f"{label}처럼 집에서 세탁하기 어려운 옷은 상품 검색 없이 전문 세탁을 권장해요. "
            f"{result.photo_request.instructions}"
        )
        return result

    result.product_lookup = ProductLookup(status="search_unavailable" if entries is None else "not_found")
    if lens_search is None and web_search is None:
        result.search_warning = "상품 검색이 연결되지 않았어요."
    if single_request:
        if search_failed:
            result.product_lookup = ProductLookup(status="search_unavailable")
        if combined:
            _, prepared, product_reading, retrieved = combined
            if official := confirm_product(prepared, product_reading, retrieved, garment, entries or ()):
                return attach_product(*official, result)
        result.search_warning = lookup_warning
        if candidates:
            result.product_lookup = ProductLookup(status="candidates", candidates=candidates[:5])
    if web_search is not None and entries and result.product_lookup.status != "matched":
        result = await lookup_web_product(result, prepared_image, web_search, entries)
    if result.product_lookup and result.product_lookup.status == "matched":
        return result
    return request_care_label_for_unmatched_product(result)


async def lookup_web_product(
    result: AnalysisResponse, image: bytes, web_search: VisionWebSearch,
    entries: Sequence[CatalogProduct],
) -> AnalysisResponse:
    try:
        web = await web_search.search(image)
    except WebSearchUnavailable:
        if result.product_lookup is None or result.product_lookup.status != "candidates":
            result.product_lookup = ProductLookup(status="search_unavailable")
        return result

    reference_product = match_web_image(web.full_image_urls(), entries)
    if reference_product:
        return attach_product(reference_product, "web_image", result)

    return result

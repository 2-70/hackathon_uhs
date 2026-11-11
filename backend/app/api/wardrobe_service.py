"""옷장 요청의 하위호환 필드와 필드별 근거를 함께 저장하는 도우미입니다."""

from base64 import b64decode
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.schemas import (
    MAX_WARDROBE_PHOTO_BYTES,
    CareFieldInput,
    ProductReference,
    WardrobeCreate,
    WardrobeUpdate,
)
from backend.app.core.errors import ApiError
from backend.app.db.models import Product, WardrobeCareField, WardrobeItem

# 기존 scalar 필드와 새 care_fields의 표준 이름을 한 곳에서 연결합니다.
SCALAR_CARE_FIELD_MAP: dict[str, str] = {
    "care_wash_method": "care_wash_method",
    "care_temperature_celsius": "care_temperature_celsius",
    "care_wash_strength": "care_wash_strength",
    "care_max_spin_rpm": "care_max_spin_rpm",
    "care_spin_level": "care_spin_level",
    "color_family": "color_family",
    "color_bleed_risk": "color_bleed_risk",
    "wash_separately": "wash_separately",
    "care_tumble_dry_allowed": "care_tumble_dry_allowed",
    "care_tumble_dry_heat": "care_tumble_dry_heat",
    "care_natural_dry": "care_natural_dry",
    "care_dry_in_shade": "care_dry_in_shade",
    "weight_grams": "weight_grams",
}

# JSON 값이 DB scalar 칼럼에 들어가기 전에 최소 자료형을 확인합니다.
SCALAR_TYPES: dict[str, type | tuple[type, ...]] = {
    "care_wash_method": str,
    "care_temperature_celsius": int,
    "care_wash_strength": str,
    "care_max_spin_rpm": int,
    "care_spin_level": str,
    "color_family": str,
    "color_bleed_risk": bool,
    "wash_separately": bool,
    "care_tumble_dry_allowed": bool,
    "care_tumble_dry_heat": str,
    "care_natural_dry": str,
    "care_dry_in_shade": bool,
    "weight_grams": int,
}


def _prepare_photo(encoded: str) -> bytes:
    try:
        data = b64decode(encoded, validate=True)
        if len(data) > MAX_WARDROBE_PHOTO_BYTES:
            raise ValueError("Photo exceeds size limit")
        with Image.open(BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("Photo exceeds pixel limit")
            image.thumbnail((2400, 2400))
            with (
                ImageOps.exif_transpose(image).convert("RGBA") as oriented,
                Image.new("RGB", oriented.size, "white") as photo,
                BytesIO() as output,
            ):
                photo.paste(oriented, mask=oriented.getchannel("A"))
                photo.save(output, "JPEG", quality=90)
                return output.getvalue()
    except (ValueError, Image.DecompressionBombError, OSError) as exc:
        raise ApiError(
            "INVALID_WARDROBE_PHOTO", "12MB 이하의 JPEG, PNG 또는 WebP 사진을 올려 주세요.", 422
        ) from exc


def _flatten_product_reference(reference: ProductReference | None) -> dict[str, Any]:
    """중첩된 상품 참조를 DB 칼럼 이름으로 바꿉니다."""

    if reference is None:
        return {
            "brand": None,
            "product_name": None,
            "product_code": None,
            "matched_product_id": None,
            "official_product_url": None,
        }
    return {
        "brand": reference.brand,
        "product_name": reference.product_name,
        "product_code": reference.product_code,
        "matched_product_id": reference.matched_product_id,
        "official_product_url": reference.official_url,
    }


def _validate_scalar_value(field_name: str, value: Any) -> None:
    """필드별 JSON 값이 대응 DB 칼럼의 기본 자료형인지 확인합니다."""

    if value is None:
        return
    expected_type = SCALAR_TYPES[field_name]
    # bool은 int의 하위 타입이므로 숫자 필드에서는 명시적으로 제외합니다.
    if expected_type is int and isinstance(value, bool):
        valid = False
    else:
        valid = isinstance(value, expected_type)
    if not valid:
        raise ApiError(
            "INVALID_CARE_FIELD",
            f"{field_name} 값의 자료형을 확인해 주세요.",
            422,
            {"field": field_name},
        )


def prepare_wardrobe_changes(
    payload: WardrobeCreate | WardrobeUpdate,
    db: Session,
) -> tuple[dict[str, Any], list[CareFieldInput] | None]:
    """요청을 scalar 변경값과 필드별 근거 목록으로 나눕니다."""

    # PATCH는 실제로 전달된 값만, POST는 기본값까지 포함해 저장합니다.
    exclude_unset = isinstance(payload, WardrobeUpdate)
    changes = payload.model_dump(exclude_unset=exclude_unset)
    photos = changes.pop("photos", None)
    for kind, photo in (photos or {}).items():
        changes[f"{kind}_photo"] = _prepare_photo(photo)
    care_fields_data = changes.pop("care_fields", None)
    reference_was_sent = "product_reference" in payload.model_fields_set
    product_data = changes.pop("product_reference", None)

    # 상품 참조가 요청에 있으면 중첩 값을 실제 칼럼으로 펼칩니다.
    if reference_was_sent:
        reference = ProductReference.model_validate(product_data) if product_data else None
        changes.update(_flatten_product_reference(reference))

    # model_dump 결과를 다시 스키마 객체로 바꿔 저장 도우미에서 일관되게 사용합니다.
    care_fields = None
    if care_fields_data is not None:
        care_fields = [CareFieldInput.model_validate(value) for value in care_fields_data]

    by_name = {field.field_name: field for field in care_fields or []}
    for scalar_name, care_name in SCALAR_CARE_FIELD_MAP.items():
        care_field = by_name.get(care_name)
        if care_field is None:
            continue
        _validate_scalar_value(scalar_name, care_field.value)
        scalar_was_sent = scalar_name in payload.model_fields_set
        # 같은 HTTP 요청 안에서 두 표현이 다르면 출처 충돌이 아니라 입력 모순입니다.
        if scalar_was_sent and changes.get(scalar_name) != care_field.value:
            raise ApiError(
                "CONFLICTING_INPUT",
                "같은 관리 필드의 scalar 값과 care_fields 값이 다릅니다.",
                422,
                {"field": scalar_name},
            )
        # 실제 출처 충돌이면 대표값을 새로 선택하지 않습니다.
        if not scalar_was_sent:
            changes[scalar_name] = (
                None if care_field.knowledge_status == "conflict" else care_field.value
            )

    # 기존 bool 필드와 새 강도 필드는 하위호환을 위해 같은 의미로 동기화합니다.
    strength_was_sent = "care_wash_strength" in changes
    gentle_was_sent = "care_gentle" in payload.model_fields_set
    if strength_was_sent and changes.get("care_wash_strength") is not None:
        expected_gentle = changes["care_wash_strength"] != "normal"
        if gentle_was_sent and changes.get("care_gentle") != expected_gentle:
            raise ApiError(
                "CONFLICTING_INPUT",
                "care_gentle과 care_wash_strength의 의미가 다릅니다.",
                422,
                {"field": "care_wash_strength"},
            )
        changes["care_gentle"] = expected_gentle
    elif gentle_was_sent and changes.get("care_gentle") is not None:
        changes["care_wash_strength"] = "gentle" if changes["care_gentle"] else "normal"

    # 연결할 공용 상품 ID가 실제로 존재하는지 저장 전에 확인합니다.
    product_id = changes.get("matched_product_id")
    if product_id and db.scalar(select(Product.id).where(Product.id == product_id)) is None:
        raise ApiError("PRODUCT_NOT_FOUND", "연결할 상품을 찾을 수 없습니다.", 404)
    return changes, care_fields


def upsert_care_fields(item: WardrobeItem, fields: list[CareFieldInput] | None) -> None:
    """의류의 필드별 근거를 이름 기준으로 추가하거나 갱신합니다."""

    if fields is None:
        return
    existing = {field.field_name: field for field in item.care_fields}
    for field_input in fields:
        stored = existing.get(field_input.field_name)
        if stored is None:
            stored = WardrobeCareField(field_name=field_input.field_name)
            item.care_fields.append(stored)
        stored.value_json = field_input.value
        stored.source_type = field_input.source_type
        stored.source_reference = field_input.source_reference
        stored.evidence = field_input.evidence
        stored.knowledge_status = field_input.knowledge_status
        stored.conflicting_values = [
            conflict.model_dump(mode="json") for conflict in field_input.conflicting_values
        ]

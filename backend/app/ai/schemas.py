from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

PhotoType = Literal["garment", "care_label", "unknown"]
RequestedPhotoType = Literal["auto", "garment", "care_label"]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
LabelText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Temperature = Annotated[int, Field(ge=1, le=100)]
WashMethod = Literal["machine_wash", "hand_wash", "do_not_wash"]
WashCycle = Literal["normal", "gentle", "very_gentle"]
DryerHeat = Literal["no_heat", "low", "normal"]
NaturalDry = Literal["line_dry", "drip_line_dry", "flat_dry", "drip_flat_dry"]
NextAction = Literal["capture_label", "retake_photo", "manual_entry"]
PhotoIssue = Literal["blurry", "glare", "cropped", "wrong_label", "missing_information"]
Value = TypeVar("Value")


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Reading(ExtractionModel, Generic[Value]):
    value: Value
    evidence: ShortText


class GarmentReadings(ExtractionModel):
    garment_type: Reading[ShortText] | None = None
    color: Reading[ShortText] | None = None
    pattern: Reading[ShortText] | None = None
    brand: Reading[ShortText] | None = None
    product_name: Reading[ShortText] | None = None
    product_code: Reading[ShortText] | None = None


class LabelReadings(ExtractionModel):
    label_text: Reading[LabelText] | None = None
    fiber_content: Reading[ShortText] | None = None
    wash_method: Reading[WashMethod] | None = None
    max_wash_temperature_c: Reading[Temperature] | None = None
    wash_cycle: Reading[WashCycle] | None = None
    bleach: Reading[ShortText] | None = None
    tumble_dry_allowed: Reading[bool] | None = None
    tumble_dry_heat: Reading[DryerHeat] | None = None
    natural_dry: Reading[NaturalDry] | None = None
    dry_in_shade: Reading[bool] | None = None
    ironing: Reading[ShortText] | None = None
    professional_cleaning: Reading[ShortText] | None = None
    special_instructions: Reading[ShortText] | None = None


class PhotoCareSuggestion(ExtractionModel):
    # Discard any unrequested wash or dry settings from an appearance-only photo.
    model_config = ConfigDict(extra="ignore", strict=True)
    sorting: Literal["similar_colors", "separate_dark_colors"] | None = None


class PhotoReadings(ExtractionModel):
    image_type: PhotoType
    garment: GarmentReadings | None = None
    care_label: LabelReadings | None = None
    photo_care: PhotoCareSuggestion | None = None
    photo_issue: PhotoIssue | None = None


class GarmentPhotoReadings(ExtractionModel):
    image_type: Literal["garment", "unknown"]
    garment: GarmentReadings | None = None
    photo_care: PhotoCareSuggestion | None = None


class CareLabelPhotoReadings(ExtractionModel):
    image_type: Literal["care_label", "unknown"]
    care_label: LabelReadings | None = None
    photo_issue: PhotoIssue | None = None


class AnalyzedField(BaseModel):
    value: str | bool | int | None
    source: Literal["garment_photo", "care_label", "official_product"]
    status: Literal["estimated", "read_from_label", "verified", "needs_confirmation"]
    evidence: str | None


class ProductInfo(BaseModel):
    id: str
    name: str
    brand: str
    color: str
    product_code: str | None = None
    source_url: HttpUrl


class ProductCandidate(BaseModel):
    name: str
    source_url: HttpUrl


class ProductLookup(BaseModel):
    status: Literal["matched", "candidates", "not_found", "search_unavailable"]
    match_method: Literal["reference_photo", "product_code", "official_url", "web_image"] | None = None
    product: ProductInfo | None = None
    candidates: list[ProductCandidate] = Field(default_factory=list)


class PhotoRequest(BaseModel):
    image_type: Literal["garment", "care_label"]
    instructions: str


class ProductMatchRequest(ExtractionModel):
    brand: ShortText | None = None
    product_code: ShortText | None = None
    source_url: HttpUrl | None = None
    garment_type: ShortText | None = None
    color: ShortText | None = None


class ProductCareResponse(BaseModel):
    product: ProductInfo
    product_care: dict[str, AnalyzedField]
    care_guidance: list[str]
    care_guidance_source: Literal["official_product"] | None = None
    photo_request: PhotoRequest | None = None
    next_actions: list[NextAction] = Field(default_factory=list)
    message: str


class AnalysisResponse(BaseModel):
    image_type: PhotoType
    status: Literal["analyzed", "needs_confirmation"]
    garment: dict[str, AnalyzedField] = Field(default_factory=dict)
    care_label: dict[str, AnalyzedField] = Field(default_factory=dict)
    product_lookup: ProductLookup | None = None
    product_care: dict[str, AnalyzedField] = Field(default_factory=dict)
    care_guidance: list[str] = Field(default_factory=list)
    care_guidance_source: Literal["estimated", "care_label", "official_product"] | None = None
    photo_request: PhotoRequest | None = None
    next_actions: list[NextAction] = Field(default_factory=list)
    message: str

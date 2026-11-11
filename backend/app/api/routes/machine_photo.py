"""세탁기 사진에서 읽은 모델명으로 등록할 모델을 찾는 API입니다."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.ai.gemini import GeminiAnalyzer, GeminiError
from backend.app.ai.machine import model_code_key, read_machine_photo
from backend.app.ai.router import MAX_UPLOAD_BYTES, get_analyzer, prepare_image
from backend.app.api.deps import DbSession
from backend.app.api.schemas import COMMON_ERROR_RESPONSES, MachineModelSummary
from backend.app.catalog_ingest.schemas import CatalogModelRead
from backend.app.db.models import CatalogModel, MachineModel

router = APIRouter(prefix="/api/machines", tags=["machines"], responses=COMMON_ERROR_RESPONSES)
MAX_CANDIDATES = 8


class MachinePhotoMatch(BaseModel):
    """사진에서 읽은 표기와 그 표기로 찾은 모델입니다."""

    status: Literal["matched", "candidates", "not_found"]
    manufacturer: str | None
    model_codes: list[str]
    catalog_models: list[CatalogModelRead]
    machines: list[MachineModelSummary]
    message: str


def find_models(db: Session, codes: list[str]) -> tuple[list, list]:
    """모델명이 같은 모델과, 접미사만 다른 비슷한 모델을 찾습니다."""

    keys = [model_code_key(code) for code in codes]
    exact, similar = {}, {}
    catalog_name = func.replace(CatalogModel.normalized_model_name, "-", "")
    for key in keys:
        # 앞 네 글자가 같은 모델만 읽고, 기호 차이는 서버에서 비교합니다.
        rows = list(db.scalars(select(CatalogModel).where(catalog_name.like(f"{key[:4]}%")).limit(300)))
        # 카탈로그에 없는 확인 모델은 수가 적어 모두 비교합니다.
        mirrored = select(CatalogModel.id).where(CatalogModel.catalog_key == MachineModel.machine_key).exists()
        rows += list(db.scalars(select(MachineModel).where(MachineModel.machine_type == "washer", ~mirrored)))
        for row in rows:
            name = model_code_key(row.model_name)
            if name == key:
                exact.setdefault(row.id, row)
            elif len(name) >= 5 and (name.startswith(key) or key.startswith(name)):
                # 색상·판매처 접미사만 다른 모델입니다. 글자 수 차이가 작을수록 가깝습니다.
                distance = abs(len(name) - len(key))
                if row.id not in similar or distance < similar[row.id][0]:
                    similar[row.id] = (distance, row)
    ranked = [row for _, row in sorted(similar.values(), key=lambda item: (item[0], item[1].model_name))]
    return list(exact.values()), [row for row in ranked if row.id not in exact]


@router.post("/identify", response_model=MachinePhotoMatch, summary="세탁기 사진으로 모델 찾기")
async def identify_machine(
    image: Annotated[UploadFile, File(description="모델명이 보이는 세탁기 사진")],
    analyzer: Annotated[GeminiAnalyzer, Depends(get_analyzer)],
    db: DbSession,
) -> MachinePhotoMatch:
    """사진에 인쇄된 모델명을 읽어 카탈로그에서 같은 모델을 찾습니다. 외형만으로 추정하지 않습니다."""

    try:
        data = await image.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await image.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail={"code": "image_too_large", "message": "40MB 이하의 사진을 올려 주세요."})
    # 작은 글씨를 읽어야 하므로 라벨 사진과 같은 해상도를 유지합니다.
    prepared, mime_type = await run_in_threadpool(prepare_image, data, "care_label")
    try:
        reading = await read_machine_photo(analyzer, prepared, mime_type)
    except GeminiError as error:
        raise HTTPException(error.status_code, detail={"code": error.code, "message": str(error)}) from None

    exact, similar = find_models(db, reading.model_codes) if reading.model_codes else ([], [])
    if len(exact) == 1:
        status, found = "matched", exact
        message = f"사진에서 {exact[0].model_name} 모델을 찾았어요."
    elif exact or similar:
        status, found = "candidates", [*exact, *similar][:MAX_CANDIDATES]
        message = f"사진에서 읽은 모델명({reading.model_codes[0]})과 비슷한 모델이에요. 내 세탁기를 골라 주세요."
    elif reading.model_codes:
        status, found = "not_found", []
        message = f"사진에서 읽은 모델명({reading.model_codes[0]})은 모델 목록에 없어요. 목록에서 직접 골라 주세요."
    else:
        status, found = "not_found", []
        message = "사진에서 모델명을 읽지 못했어요. 모델명 스티커를 가까이 찍거나 목록에서 직접 골라 주세요."
    return MachinePhotoMatch(
        status=status, manufacturer=reading.manufacturer, model_codes=reading.model_codes,
        catalog_models=[CatalogModelRead.model_validate(row) for row in found if isinstance(row, CatalogModel)],
        machines=[MachineModelSummary.model_validate(row) for row in found if isinstance(row, MachineModel)],
        message=message,
    )

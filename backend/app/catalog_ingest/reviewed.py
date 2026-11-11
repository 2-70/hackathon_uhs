"""공식 설명서에서 검토한 세탁 방법과 코스 기본 설정을 적재합니다."""

import argparse
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    CatalogDocument,
    CatalogModel,
    CatalogModelDocument,
    CatalogUsageInstruction,
)
from backend.app.db.session import SessionLocal
from backend.seed.load_verified import (
    CourseSeed,
    MachineModelSeed,
    SettingSeed,
    upsert_machine_model,
)

LG_WASHTOWER_MANUAL = "https://gscs-b2c.lge.com/open/downloadFile?fileId=aYgXp4bXIhCWq82n4TlDPw"

# 설명서 한 권의 내용은 한 곳에서 관리하고, 제조사가 정확히 연결한 모델에만 적용합니다.
LG_WASHTOWER_INSTRUCTIONS = (
    (
        "start_sequence", 21, "세탁 시작",
        (
            "전원을 켜고 세탁 코스 선택 버튼으로 코스를 고르세요. "
            "설정을 확인한 뒤 시작/일시정지 버튼을 누르세요."
        ),
    ),
    (
        "course_selection", 22, "코스 고르기",
        (
            "일반 세탁물에는 표준 코스를 사용하세요. 물세탁 가능한 이불이나 담요는 "
            "일반 세탁물과 분리하고, 이불 코스로 한 장씩 4 kg 이하만 넣으세요."
        ),
    ),
    (
        "option_settings", 27, "표준 코스 설정",
        (
            "표준 코스의 기본값은 물 온도 40°C, 헹굼 2회, 탈수 강입니다. "
            "물온도 버튼으로 냉수(Co), 30°C, 40°C, 60°C를 선택할 수 있습니다. "
            "옷 라벨의 한도에 맞춰 온도와 탈수 단계를 확인하세요."
        ),
    ),
    (
        "option_settings", 28, "소량급속 코스 설정",
        (
            "소량급속 코스의 기본값은 물 온도 40°C, 헹굼 1회, 탈수 중입니다. "
            "물온도 버튼에서 냉수(Co), 30°C 또는 40°C를 고를 수 있습니다."
        ),
    ),
)


def apply_lg_washtower_review(db: Session, *, commit: bool) -> int:
    """공식 연결이 확인된 모델의 안내와 표준 코스 기본 조합을 저장합니다."""

    matches = db.execute(
        select(CatalogModel, CatalogDocument)
        .join(CatalogModelDocument, CatalogModelDocument.catalog_model_id == CatalogModel.id)
        .join(CatalogDocument, CatalogDocument.id == CatalogModelDocument.document_id)
        .where(
            CatalogDocument.source_url == LG_WASHTOWER_MANUAL,
            CatalogModelDocument.exact_model_match.is_(True),
            CatalogModelDocument.matching_status == "confirmed",
        )
    ).all()
    if not commit:
        return len({model.id for model, _ in matches})

    for model, document in matches:
        for category, page, title, text in LG_WASHTOWER_INSTRUCTIONS:
            key = hashlib.sha256(f"lg-mfl71831422|{category}|{page}".encode()).hexdigest()
            instruction = db.scalar(select(CatalogUsageInstruction).where(
                CatalogUsageInstruction.catalog_model_id == model.id,
                CatalogUsageInstruction.document_id == document.id,
                CatalogUsageInstruction.instruction_key == key,
            ))
            if instruction is None:
                instruction = CatalogUsageInstruction(
                    catalog_model_id=model.id, document_id=document.id, instruction_key=key,
                )
                db.add(instruction)
            instruction.category = category
            instruction.title = title
            instruction.instruction_text = text
            instruction.page_number = page
            instruction.review_status = "confirmed"

        # 기본값으로 동시에 확인된 조합만 계획에 사용합니다.
        upsert_machine_model(db, MachineModelSeed(
            machine_key=model.catalog_key,
            machine_type="washer",
            manufacturer="LG전자",
            model_name=model.model_name,
            source_url=LG_WASHTOWER_MANUAL,
            verification_status="confirmed",
            verified_scope="LG 사용설명서 MFL71831422의 표준 코스 기본 조합",
            courses=[CourseSeed(
                course_key="normal",
                name="표준",
                settings=[SettingSeed(
                    temperature_celsius=40,
                    wash_strength="normal",
                    spin_level="강",
                    is_default=True,
                    verification_status="confirmed",
                    manual_page=27,
                    source_url=f"{LG_WASHTOWER_MANUAL}#page=27",
                )],
            )],
        ))
        model.recommendation_status = "verified_options"
    db.commit()
    return len({model.id for model, _ in matches})


def main() -> None:
    parser = argparse.ArgumentParser(description="검토한 공식 세탁기 설명서 설정 적용")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        print(f"matched_models={apply_lg_washtower_review(db, commit=args.commit)}")


if __name__ == "__main__":
    main()

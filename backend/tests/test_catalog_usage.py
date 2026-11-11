"""공식 설명서 HTML과 사용법 범주 추출을 검증합니다."""

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.catalog_ingest import usage
from backend.app.catalog_ingest.usage import (
    DocumentTarget,
    DownloadResult,
    InstructionTemplate,
    PreparedDocument,
    extract_html_text,
    extract_instruction_templates,
    extract_pdf_templates,
)
from backend.app.db.models import (
    CatalogDocument,
    CatalogModel,
    CatalogModelDocument,
    CatalogUsageInstruction,
    new_id,
)


def test_html_text_ignores_scripts():
    """화면에 보이지 않는 스크립트 문구는 사용법 근거가 될 수 없습니다."""

    content = """
    <html><body>
      <script>var text = '세제를 넣으세요';</script>
      <p>세탁물에 맞는 세제를 권장량만큼 넣으세요.</p>
    </body></html>
    """.encode()
    text = extract_html_text(content)
    assert "var text" not in text
    assert "세탁물에 맞는 세제" in text


def test_extract_instruction_templates_skips_time_values():
    """범주별 공식 문장은 저장하되 사용자가 제외한 시간값은 넣지 않아야 합니다."""

    pages = [
        (
            5,
            (
                "세탁물에 맞는 세제를 권장량만큼 세제함에 넣으세요.\n"
                "세탁 코스별 선택 가능 설정 및 옵션\n"
                "전원을 켠 다음 원하는 코스를 선택하고 시작 버튼을 누르세요.\n"
                "표준 코스의 예상 소요 시간은 60분입니다.\n"
                "필터 청소를 정기적으로 실시해 제품을 깨끗하게 관리하세요."
            ),
        )
    ]
    templates = extract_instruction_templates(pages)
    assert {item.category for item in templates} >= {
        "start_sequence",
        "detergent",
        "course_selection",
        "maintenance",
    }
    assert all("60분" not in item.instruction_text for item in templates)
    assert all("선택 가능 설정 및 옵션" not in item.instruction_text for item in templates)
    assert all(item.page_number == 5 for item in templates)


def test_instruction_filter_rejects_broken_multilingual_and_toc_lines():
    """깨진 문자·다국어 우세 본문·목차 점선을 한글 사용법으로 저장하지 않습니다."""

    assert not usage._safe_instruction_line("세제를 � 표시선까지 넣고 세탁을 시작하세요.")
    assert not usage._safe_instruction_line(
        "使用洗涤桶消毒程序来清洁洗涤桶并按下 통세척 버튼을 누르세요."
    )
    assert not usage._safe_instruction_line(
        "Nhấn nút nguồn rồi chọn 동작/일시정지 버튼을 누르세요 để bắt đầu."
    )
    assert not usage._safe_instruction_line(
        "세탁 코스별 설명 . . . . . . . . . . . . . . . . . . . . . . 25"
    )
    assert usage._safe_instruction_line(
        "세탁물에 맞는 세제를 권장량만큼 세제함에 넣고 시작 버튼을 누르세요."
    )


def test_pdf_extraction_stops_after_all_categories(monkeypatch):
    """필요한 6개 범주를 모두 찾으면 뒤쪽 PDF 페이지는 읽지 않습니다."""

    first_page_text = (
        "전원을 켠 다음 세탁을 시작하려면 동작/일시정지 버튼을 누르세요.\n"
        "세탁물에 맞는 세제를 권장량만큼 세제함에 넣으세요.\n"
        "세탁 코스를 선택한 다음 원하는 코스 버튼을 누르세요.\n"
        "물 온도와 헹굼 및 탈수 옵션을 확인하고 선택하세요.\n"
        "제품 가까이에서 불을 사용하지 마세요. 화재 위험이 있습니다.\n"
        "필터 청소를 정기적으로 실시해 제품을 깨끗하게 관리하세요."
    )

    class FakePage:
        def __init__(self, text: str, should_fail: bool = False) -> None:
            self.text = text
            self.should_fail = should_fail

        def extract_text(self) -> str:
            if self.should_fail:
                raise AssertionError("모든 범주 확보 후 페이지를 읽었습니다.")
            return self.text

    class FakeReader:
        def __init__(self) -> None:
            self.pages = [FakePage(first_page_text), FakePage("", True), FakePage("", True)]

    monkeypatch.setattr(usage, "PdfReader", lambda *_args, **_kwargs: FakeReader())

    templates, page_count, text_chars = extract_pdf_templates(b"%PDF-test")

    assert len(templates) == len(usage.CATEGORY_RULES)
    assert page_count == 3
    assert text_chars == len(first_page_text)


def test_store_batch_uses_short_fresh_session(db_session, monkeypatch):
    """긴 다운로드 뒤에는 새 세션으로 문서 상태를 저장해 유휴 연결 종료를 피합니다."""

    document_id = new_id()
    db_session.add(
        CatalogDocument(
            id=document_id,
            document_key="test-document",
            source_url="https://example.com/manual.pdf",
            title="테스트 설명서",
            language="ko",
            media_type="application/pdf",
            retrieval_status="pending",
            extraction_status="pending",
            raw_metadata={},
        )
    )
    db_session.commit()
    # 실제 수집기처럼 호출 시점마다 독립 세션을 만들도록 테스트용 팩토리를 연결합니다.
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(usage, "SessionLocal", testing_session_local)
    prepared = PreparedDocument(
        target=DocumentTarget(
            id=document_id,
            source_url="https://example.com/manual.pdf",
            media_type="application/pdf",
        ),
        result=DownloadResult(
            document_id=document_id,
            status="download_failed",
            error="테스트 네트워크 오류",
        ),
    )

    progress_path = Path(".tmp/test-catalog-usage-progress.json")
    counts = asyncio.run(usage._store_prepared_batch([prepared], progress_path))

    db_session.expire_all()
    stored = db_session.get(CatalogDocument, document_id)
    assert counts["not_extracted"] == 1
    assert stored is not None and stored.retrieval_status == "download_failed"
    assert stored.raw_metadata == {"retrieval_error": "테스트 네트워크 오류"}
    # 반복 실행 시 테스트 산출물이 실제 수집 진행 파일과 섞이지 않도록 정리합니다.
    progress_path.unlink(missing_ok=True)


def test_reprocess_replaces_same_instruction_key_without_duplicate(db_session, monkeypatch):
    """재처리는 기존 자동 행을 먼저 삭제해 같은 안정 키를 중복 삽입하지 않습니다."""

    model_id = new_id()
    document_id = new_id()
    instruction_key = "a" * 64
    db_session.add_all(
        [
            CatalogModel(
                id=model_id,
                catalog_key="test-model",
                machine_family="drum",
                model_name="TEST-100",
                normalized_model_name="TEST100",
                source_url="https://example.com/model",
            ),
            CatalogDocument(
                id=document_id,
                document_key="test-reprocess-document",
                source_url="https://example.com/reprocess.pdf",
                title="재처리 설명서",
                language="ko",
                media_type="application/pdf",
                retrieval_status="retrieved",
                extraction_status="structured",
                raw_metadata={},
            ),
            CatalogModelDocument(
                id=new_id(),
                catalog_model_id=model_id,
                document_id=document_id,
                matching_method="exact_model",
                matching_status="confirmed",
                exact_model_match=True,
            ),
            CatalogUsageInstruction(
                id=new_id(),
                catalog_model_id=model_id,
                document_id=document_id,
                instruction_key=instruction_key,
                category="detergent",
                title="세제·섬유유연제",
                instruction_text="기존 자동 추출 문장입니다.",
                page_number=3,
                evidence_excerpt="기존 자동 추출 문장입니다.",
                review_status="needs_review",
            ),
        ]
    )
    db_session.commit()
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(usage, "SessionLocal", testing_session_local)
    prepared = PreparedDocument(
        target=DocumentTarget(
            id=document_id,
            source_url="https://example.com/reprocess.pdf",
            media_type="application/pdf",
        ),
        result=DownloadResult(
            document_id=document_id,
            status="downloaded",
            content=b"updated manual",
            content_sha256="b" * 64,
        ),
        templates=[
            InstructionTemplate(
                instruction_key=instruction_key,
                category="detergent",
                title="세제·섬유유연제",
                instruction_text="세탁물에 맞는 세제를 권장량만큼 세제함에 넣으세요.",
                page_number=4,
                evidence_excerpt="세탁물에 맞는 세제를 권장량만큼 세제함에 넣으세요.",
            )
        ],
        page_count=10,
        text_chars=100,
    )

    progress_path = Path(".tmp/test-catalog-reprocess-progress.json")
    asyncio.run(usage._store_prepared_batch([prepared], progress_path))

    db_session.expire_all()
    stored = list(
        db_session.scalars(
            select(CatalogUsageInstruction).where(
                CatalogUsageInstruction.catalog_model_id == model_id,
                CatalogUsageInstruction.document_id == document_id,
                CatalogUsageInstruction.instruction_key == instruction_key,
            )
        )
    )
    assert len(stored) == 1
    assert stored[0].instruction_text.endswith("넣으세요.")
    assert stored[0].page_number == 4
    progress_path.unlink(missing_ok=True)


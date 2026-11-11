"""공식 설명서에서 짧은 모델별 사용법 근거를 구조화해 Neon에 저장합니다."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import httpx
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    CatalogDocument,
    CatalogModelDocument,
    CatalogUsageInstruction,
    new_id,
    utc_now,
)
from backend.app.db.session import SessionLocal

# 앱이 바로 분류해서 보여줄 수 있는 사용법 범주와 공식 문서 검색어입니다.
CATEGORY_RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "start_sequence": ("세탁 시작 순서", ("전원을", "동작/일시정지", "시작 버튼", "세탁을 시작")),
    "detergent": ("세제·섬유유연제", ("세제", "섬유유연제", "유연제")),
    "course_selection": ("세탁 코스 선택", ("코스를 선택", "세탁 코스", "표준 코스", "코스 버튼")),
    "option_settings": ("온도·헹굼·탈수 설정", ("물 온도", "세탁 온도", "헹굼", "탈수", "옵션")),
    "warning": ("안전 주의사항", ("경고", "주의", "하지 마세요", "위험")),
    "maintenance": ("청소·관리", ("통세척", "필터 청소", "세탁조 청소", "제품 청소", "관리 방법")),
}


@dataclass(frozen=True)
class InstructionTemplate:
    """문서 한 개에서 찾은 짧은 사용법 사실과 페이지 근거입니다."""

    instruction_key: str
    category: str
    title: str
    instruction_text: str
    page_number: int | None
    evidence_excerpt: str


@dataclass
class DownloadResult:
    """문서 다운로드 결과이며 원문 바이트는 DB에 저장하지 않습니다."""

    document_id: str
    status: str
    content: bytes | None = None
    content_type: str | None = None
    content_sha256: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class DocumentTarget:
    """긴 네트워크 작업 중 DB 세션을 잡아두지 않기 위한 문서 식별 정보입니다."""

    id: str
    source_url: str
    media_type: str | None


@dataclass
class PreparedDocument:
    """다운로드·텍스트 추출을 끝내고 짧은 DB 트랜잭션만 남긴 결과입니다."""

    target: DocumentTarget
    result: DownloadResult
    templates: list[InstructionTemplate] | None = None
    page_count: int | None = None
    text_chars: int = 0


class VisibleTextParser(HTMLParser):
    """공식 HTML 설명서에서 스크립트·스타일을 제외한 표시 텍스트만 읽습니다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and lowered in {
            "p",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "br",
            "section",
            "article",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif self._ignored_depth == 0 and lowered in {"p", "li", "section", "article"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        """연속 공백을 줄이되 문단 경계는 유지합니다."""

        lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


def decode_html(content: bytes) -> str:
    """국내 공식 사이트의 UTF-8을 우선하고 깨짐이 많으면 CP949를 시도합니다."""

    utf8 = content.decode("utf-8", errors="replace")
    if utf8.count("�") <= 5:
        return utf8
    return content.decode("cp949", errors="replace")


def extract_html_text(content: bytes) -> str:
    """HTML 원문에서 화면에 표시되는 텍스트를 추출합니다."""

    parser = VisibleTextParser()
    parser.feed(decode_html(content))
    return parser.text()


def extract_pdf_pages(content: bytes) -> list[tuple[int, str]]:
    """PDF 각 페이지의 텍스트를 읽고 페이지 번호와 함께 반환합니다."""

    reader = PdfReader(io.BytesIO(content), strict=False)
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append((index, page.extract_text() or ""))
    return pages


def extract_pdf_templates(
    content: bytes,
) -> tuple[list[InstructionTemplate], int, int]:
    """페이지 순서대로 사용법을 찾고 모든 범주가 확보되면 불필요한 추출을 멈춥니다."""

    reader = PdfReader(io.BytesIO(content), strict=False)
    page_count = len(reader.pages)
    templates: list[InstructionTemplate] = []
    seen_categories: set[str] = set()
    extracted_text_chars = 0
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        extracted_text_chars += len(text)
        for template in extract_instruction_templates([(page_number, text)]):
            if template.category in seen_categories:
                continue
            templates.append(template)
            seen_categories.add(template.category)
        # 이 기능은 전체 본문 검색이 아니라 정해진 6개 사용법 범주 수집이므로 여기서 종료할 수 있습니다.
        if len(seen_categories) == len(CATEGORY_RULES):
            break
    return templates, page_count, extracted_text_chars


def _candidate_lines(text: str) -> list[str]:
    """너무 짧은 제목과 지나치게 긴 본문을 제외한 근거 후보를 만듭니다."""

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" -•·\t")
        if 20 <= len(line) <= 450:
            lines.append(line)
    return lines


def _safe_instruction_line(line: str) -> bool:
    """탐색 메뉴·저작권·시간값을 사용법으로 잘못 저장하지 않게 걸러냅니다."""

    blocked = ("개인정보", "저작권", "copyright", "검색어", "로그인", "회원가입", "고객지원 홈")
    lowered = line.lower()
    if any(value in lowered for value in blocked):
        return False
    # 문자 매핑 실패와 목차의 점선 안내는 실제 사용 절차가 아니므로 저장하지 않습니다.
    if "�" in line or re.search(r"(?:[.·∙…]\s*){5,}\d", line):
        return False
    hangul_count = len(re.findall(r"[가-힣]", line))
    han_count = len(re.findall(r"[一-龥]", line))
    latin_count = len(re.findall(r"[A-Za-z\u00c0-\u024f\u1e00-\u1eff]", line))
    # 국내 사용법 API에는 한글보다 중국어·베트남어 등이 많은 다국어 문장을 넣지 않습니다.
    if han_count > hangul_count or latin_count > max(12, int(hangul_count * 1.5)):
        return False
    # 짧은 메뉴 제목은 구조화 완료로 세지 않고 실제 절차·설명이 있는 문장만 허용합니다.
    actionable_endings = (
        "하세요",
        "마세요",
        "됩니다",
        "합니다",
        "누르세요",
        "넣으세요",
        "선택하세요",
        "사용하세요",
        "확인하세요",
    )
    if len(line) < 35 and not any(ending in line for ending in actionable_endings):
        return False
    # 사용자가 제외한 세탁·건조 예상시간 기능과 혼동될 수 있는 숫자 시간 문장은 저장하지 않습니다.
    return re.search(r"\d+\s*(분|시간)|남은\s*시간|소요\s*시간", line) is None


def extract_instruction_templates(
    pages: list[tuple[int | None, str]],
) -> list[InstructionTemplate]:
    """범주별로 가장 먼저 확인된 짧은 공식 근거 한 건씩만 구조화합니다."""

    templates: list[InstructionTemplate] = []
    seen_categories: set[str] = set()
    for page_number, text in pages:
        for line in _candidate_lines(text):
            if not _safe_instruction_line(line):
                continue
            for category, (title, keywords) in CATEGORY_RULES.items():
                if category in seen_categories:
                    continue
                if not any(keyword.lower() in line.lower() for keyword in keywords):
                    continue
                excerpt = line[:500]
                identity = f"{category}|{page_number}|{excerpt}"
                templates.append(
                    InstructionTemplate(
                        instruction_key=hashlib.sha256(identity.encode()).hexdigest(),
                        category=category,
                        title=title,
                        instruction_text=excerpt,
                        page_number=page_number,
                        evidence_excerpt=excerpt,
                    )
                )
                seen_categories.add(category)
    return templates


async def _download_document(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    document: DocumentTarget,
    max_bytes: int,
) -> DownloadResult:
    """용량 제한을 지키며 문서를 메모리로만 받아 해시를 계산합니다."""

    async with semaphore:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with client.stream("GET", document.source_url) as response:
                    response.raise_for_status()
                    declared_size = int(response.headers.get("Content-Length", "0") or 0)
                    if declared_size > max_bytes:
                        return DownloadResult(
                            document.id,
                            "too_large",
                            error=f"content_length={declared_size}",
                        )
                    chunks: list[bytes] = []
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > max_bytes:
                            return DownloadResult(
                                document.id,
                                "too_large",
                                error=f"received_bytes>{max_bytes}",
                            )
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    if not content:
                        raise ValueError("공식 문서 응답이 비어 있습니다.")
                    return DownloadResult(
                        document.id,
                        "downloaded",
                        content=content,
                        content_type=response.headers.get("Content-Type"),
                        content_sha256=hashlib.sha256(content).hexdigest(),
                    )
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
        return DownloadResult(
            document.id,
            "download_failed",
            error=f"{type(last_error).__name__}: {last_error}",
        )


async def _extract_templates(
    document: DocumentTarget,
    result: DownloadResult,
) -> tuple[list[InstructionTemplate], int | None, int]:
    """문서 형식에 맞게 텍스트를 읽고 구조화 후보를 반환합니다."""

    assert result.content is not None
    is_pdf = result.content.startswith(b"%PDF") or document.media_type == "application/pdf"
    if is_pdf:
        return await asyncio.to_thread(extract_pdf_templates, result.content)
    html_text = await asyncio.to_thread(extract_html_text, result.content)
    templates = extract_instruction_templates([(None, html_text)])
    return templates, None, len(html_text)


def _store_document_result(
    db: Session,
    document: CatalogDocument,
    result: DownloadResult,
    templates: list[InstructionTemplate],
    page_count: int | None,
    text_chars: int,
) -> int:
    """문서 상태와 연결된 모든 정확 모델의 구조화 사용법을 멱등 저장합니다."""

    metadata = dict(document.raw_metadata or {})
    metadata.update(
        {
            "download_bytes": len(result.content or b""),
            "extracted_text_chars": text_chars,
            "structured_category_count": len(templates),
        }
    )
    document.raw_metadata = metadata
    document.content_sha256 = result.content_sha256
    document.page_count = page_count
    document.retrieval_status = "retrieved"
    document.extraction_status = "structured" if templates else "no_structured_content"
    document.retrieved_at = utc_now()
    model_ids = list(
        db.scalars(
            select(CatalogModelDocument.catalog_model_id).where(
                CatalogModelDocument.document_id == document.id,
                CatalogModelDocument.matching_status == "confirmed",
                CatalogModelDocument.exact_model_match.is_(True),
            )
        )
    )
    existing_keys = set(
        db.execute(
            select(
                CatalogUsageInstruction.catalog_model_id,
                CatalogUsageInstruction.instruction_key,
            ).where(CatalogUsageInstruction.document_id == document.id)
        ).all()
    )
    # 재처리 시 이전 자동 추출 후보만 교체하고 사람이 확인한 행은 절대 삭제하지 않습니다.
    previous_generated = list(
        db.scalars(
            select(CatalogUsageInstruction).where(
                CatalogUsageInstruction.document_id == document.id,
                CatalogUsageInstruction.review_status == "needs_review",
            )
        )
    )
    for item in previous_generated:
        existing_keys.discard((item.catalog_model_id, item.instruction_key))
        db.delete(item)
    if previous_generated:
        # 같은 고유 키를 다시 추가할 때 INSERT가 DELETE보다 먼저 실행되지 않도록 순서를 확정합니다.
        db.flush()
    inserted = 0
    for model_id in model_ids:
        for template in templates:
            key = (model_id, template.instruction_key)
            if key in existing_keys:
                continue
            db.add(
                CatalogUsageInstruction(
                    id=new_id(),
                    catalog_model_id=model_id,
                    document_id=document.id,
                    instruction_key=template.instruction_key,
                    category=template.category,
                    title=template.title,
                    instruction_text=template.instruction_text,
                    page_number=template.page_number,
                    evidence_excerpt=template.evidence_excerpt,
                    # 자동 추출은 공식 문서 근거가 있어도 사람이 표본 검토하기 전에는 확정하지 않습니다.
                    review_status="needs_review",
                )
            )
            existing_keys.add(key)
            inserted += 1
    return inserted


def _mark_download_failure(document: CatalogDocument, result: DownloadResult) -> None:
    """큰 파일과 네트워크 실패를 서로 다른 재처리 상태로 남깁니다."""

    document.retrieval_status = result.status
    document.extraction_status = "not_extracted"
    metadata = dict(document.raw_metadata or {})
    metadata["retrieval_error"] = result.error
    document.raw_metadata = metadata


def _write_progress(path: Path, db: Session) -> dict[str, int]:
    """문서 처리·사용법 저장 수를 비밀정보 없는 JSON으로 기록합니다."""

    status_rows = db.execute(
        select(CatalogDocument.extraction_status, func.count(CatalogDocument.id)).group_by(
            CatalogDocument.extraction_status
        )
    )
    status_counts = {str(status): int(count) for status, count in status_rows}
    instruction_count = int(
        db.scalar(select(func.count()).select_from(CatalogUsageInstruction)) or 0
    )
    payload = {
        "scope": "KR official washer usage extraction",
        "updated_at": utc_now().isoformat(),
        "document_status_counts": status_counts,
        "structured_instruction_rows": instruction_count,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**status_counts, "instruction_rows": instruction_count}


async def _store_prepared_batch(
    prepared: list[PreparedDocument],
    progress_file: Path,
) -> dict[str, int]:
    """Neon 연결이 끊겨도 새 세션으로 같은 배치를 안전하게 다시 저장합니다."""

    for attempt in range(3):
        db = SessionLocal()
        try:
            # 다운로드 중에는 DB 연결을 보유하지 않고, 저장 직전에 최신 ORM 객체를 다시 읽습니다.
            document_ids = [item.target.id for item in prepared]
            documents = {
                document.id: document
                for document in db.scalars(
                    select(CatalogDocument).where(CatalogDocument.id.in_(document_ids))
                )
            }
            for item in prepared:
                document = documents.get(item.target.id)
                if document is None:
                    continue
                if item.result.status != "downloaded" or item.result.content_sha256 is None:
                    _mark_download_failure(document, item.result)
                    continue
                _store_document_result(
                    db,
                    document,
                    item.result,
                    item.templates or [],
                    item.page_count,
                    item.text_chars,
                )
            db.commit()
            return _write_progress(progress_file, db)
        except OperationalError:
            # 커밋되지 않은 트랜잭션은 전부 되돌리고 새 연결로 같은 멱등 배치를 재시도합니다.
            db.rollback()
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (2**attempt))
        finally:
            db.close()
    raise RuntimeError("문서 저장 재시도 횟수를 초과했습니다.")


async def _prepare_document(
    document: DocumentTarget,
    result: DownloadResult,
    template_cache: dict[str, tuple[list[InstructionTemplate], int | None, int]],
    extraction_semaphore: asyncio.Semaphore,
) -> PreparedDocument:
    """다운로드 결과를 DB와 무관하게 구조화하며 문서별 CPU 작업도 제한 병렬화합니다."""

    if result.status != "downloaded" or result.content_sha256 is None:
        return PreparedDocument(target=document, result=result)
    cached = template_cache.get(result.content_sha256)
    if cached is None:
        try:
            # 대용량 PDF 여러 개가 동시에 메모리를 과도하게 쓰지 않도록 CLI 동시성 값을 공유합니다.
            async with extraction_semaphore:
                cached = await _extract_templates(document, result)
        except (OSError, PyPdfError, ValueError) as exc:
            result.status = "extract_failed"
            result.error = f"{type(exc).__name__}: {exc}"
            return PreparedDocument(target=document, result=result)
        template_cache[result.content_sha256] = cached
    templates, page_count, text_chars = cached
    return PreparedDocument(
        target=document,
        result=result,
        templates=templates,
        page_count=page_count,
        text_chars=text_chars,
    )


async def _run_batches(
    documents: list[DocumentTarget],
    *,
    concurrency: int,
    batch_size: int,
    max_bytes: int,
    progress_file: Path,
) -> dict[str, int]:
    """다운로드·해시 중복제거·텍스트 추출·DB 저장을 작은 배치로 수행합니다."""

    semaphore = asyncio.Semaphore(concurrency)
    extraction_semaphore = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    template_cache: dict[str, tuple[list[InstructionTemplate], int | None, int]] = {}
    headers = {"User-Agent": "WashWiseUsageCollector/0.1"}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(90.0),
        follow_redirects=True,
        limits=limits,
        headers=headers,
    ) as client:
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            results = await asyncio.gather(
                *[
                    _download_document(client, semaphore, document, max_bytes)
                    for document in batch
                ]
            )
            prepared = list(
                await asyncio.gather(
                    *[
                        _prepare_document(
                            document,
                            result,
                            template_cache,
                            extraction_semaphore,
                        )
                        for document, result in zip(batch, results, strict=True)
                    ]
                )
            )
            counts = await _store_prepared_batch(prepared, progress_file)
            # DB에 크기·해시·사용법을 저장한 뒤 원문 참조를 끊어 메모리와 원문 재배포를 줄입니다.
            for item in prepared:
                item.result.content = None
            print(
                json.dumps(
                    {
                        "stage": "usage_extraction",
                        "processed": min(start + batch_size, len(documents)),
                        "total": len(documents),
                        **counts,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    db = SessionLocal()
    try:
        return _write_progress(progress_file, db)
    finally:
        db.close()


def run_extraction(
    *,
    concurrency: int,
    batch_size: int,
    max_megabytes: int,
    retry_failed: bool,
    reprocess: bool,
    reprocess_invalid: bool,
    limit: int | None,
    progress_file: Path,
) -> dict[str, int]:
    """pending 문서를 처리하고 선택적으로 실패 문서를 다시 시도합니다."""

    db = SessionLocal()
    try:
        if reprocess_invalid:
            # 현재 저장된 짧은 근거에 새 품질 필터를 적용해 영향받는 문서만 다시 읽습니다.
            generated_rows = db.execute(
                select(
                    CatalogUsageInstruction.document_id,
                    CatalogUsageInstruction.instruction_text,
                ).where(CatalogUsageInstruction.review_status == "needs_review")
            )
            invalid_document_ids = {
                document_id
                for document_id, instruction_text in generated_rows
                if not _safe_instruction_line(instruction_text)
            }
            statement = select(CatalogDocument).where(
                CatalogDocument.id.in_(invalid_document_ids)
            )
        else:
            statuses = ["structured", "no_structured_content"] if reprocess else ["pending"]
            if retry_failed:
                statuses.extend(["not_extracted"])
            statement = select(CatalogDocument).where(
                CatalogDocument.extraction_status.in_(statuses)
            )
        statement = statement.order_by(
            # HTML 설명서를 먼저 처리해 빠르게 구조화 사용법을 확보합니다.
            CatalogDocument.media_type.desc(),
            CatalogDocument.id,
        )
        if limit is not None:
            statement = statement.limit(limit)
        documents = [
            DocumentTarget(
                id=document.id,
                source_url=document.source_url,
                media_type=document.media_type,
            )
            for document in db.scalars(statement)
        ]
    finally:
        # 수백 쪽 PDF를 처리하는 동안 Neon 연결이 유휴 종료되지 않도록 먼저 세션을 반환합니다.
        db.close()
    if not documents:
        db = SessionLocal()
        try:
            return _write_progress(progress_file, db)
        finally:
            db.close()
    return asyncio.run(
        _run_batches(
            documents,
            concurrency=concurrency,
            batch_size=batch_size,
            max_bytes=max_megabytes * 1024 * 1024,
            progress_file=progress_file,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    """공식 사이트 부하와 메모리 사용량을 안전한 범위에서 조절합니다."""

    parser = argparse.ArgumentParser(description="공식 세탁기 설명서 사용법 구조화")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--max-megabytes", type=int, default=30)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument(
        "--reprocess-invalid",
        action="store_true",
        help="현재 품질 필터에 걸리는 자동 행이 있는 문서만 재처리",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=Path(".tmp/usage-progress.json"),
    )
    return parser


def main() -> int:
    """공식 설명서 구조화를 실행하고 실제 DB 상태를 출력합니다."""

    args = build_parser().parse_args()
    if args.concurrency < 1 or args.concurrency > 5:
        raise SystemExit("--concurrency는 1~5 사이여야 합니다.")
    if args.batch_size < 1 or args.batch_size > 50:
        raise SystemExit("--batch-size는 1~50 사이여야 합니다.")
    if args.max_megabytes < 1 or args.max_megabytes > 100:
        raise SystemExit("--max-megabytes는 1~100 사이여야 합니다.")
    counts = run_extraction(
        concurrency=args.concurrency,
        batch_size=args.batch_size,
        max_megabytes=args.max_megabytes,
        retry_failed=args.retry_failed,
        reprocess=args.reprocess,
        reprocess_invalid=args.reprocess_invalid,
        limit=args.limit,
        progress_file=args.progress_file,
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


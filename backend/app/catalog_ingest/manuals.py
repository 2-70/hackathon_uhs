"""국내 공식 고객지원에서 모델별 사용설명서를 매칭합니다."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.catalog_ingest.kea import normalize_model_name
from backend.app.db.models import (
    CatalogDocument,
    CatalogModel,
    CatalogModelDocument,
    new_id,
    utc_now,
)
from backend.app.db.session import SessionLocal

LG_MANUAL_API = "https://www.lge.co.kr/support/manuals/searchManualDriver.lgajax"
SAMSUNG_MODEL_URL = "https://www.samsung.com/sec/support/model/{model_name}/"
SAMSUNG_MANUAL_API = "https://www.samsung.com/sec/xhr/goods/goodsManual"
QAID_MANUAL_LIST = "https://www.q-aid.co.kr/solution/manualList"
QAID_DOWNLOAD = "https://www.q-aid.co.kr/file/download"
QAID_WASHER_CATEGORY = "002014001"


@dataclass(frozen=True)
class ManualDocumentCandidate:
    """공식 사이트가 특정 모델에 연결해 반환한 설명서 메타데이터입니다."""

    document_key: str
    source_url: str
    title: str | None
    language: str | None
    media_type: str | None
    model_scope_text: str | None
    matching_method: str
    raw_metadata: dict


@dataclass(frozen=True)
class ManualMatchResult:
    """모델 한 개의 공식 설명서 검색 결과입니다."""

    model_id: str
    adapter: str | None
    status: str
    documents: tuple[ManualDocumentCandidate, ...] = ()
    note: str | None = None


def _normalize_company(value: str | None) -> str:
    """공식 업체명에서 공백과 전각문자 차이만 제거합니다."""

    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).upper()


def select_adapter(model: CatalogModel) -> str | None:
    """공식 업체 근거에 따라 해당 고객지원 자료를 선택합니다."""

    companies = [_normalize_company(model.applicant_name), _normalize_company(model.manufacturer_name)]
    if any(company.startswith("LG") or "LG전자" in company for company in companies if company):
        return "lg"
    if any("삼성전자" in company for company in companies if company):
        return "samsung"
    if any(
        provider in company
        for company in companies
        for provider in ("위니아", "대우전자", "큐에이드", "WINIA", "DAEWOOELECTRONICS", "QAID")
    ):
        return "qaid"
    return None


def _media_type(file_type: str, url: str) -> str | None:
    """공식 파일 형식 표기를 표준 MIME 형식으로 바꿉니다."""

    lowered = f"{file_type} {url}".lower()
    if "pdf" in lowered:
        return "application/pdf"
    if "html" in lowered:
        return "text/html"
    if "zip" in lowered:
        return "application/zip"
    return None


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 3,
    **kwargs,
) -> httpx.Response:
    """일시적인 공식 사이트 오류만 제한적으로 재시도합니다."""

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = await client.request(method, url, **kwargs)
            # 존재하지 않는 모델의 명시적인 404는 재시도하지 않습니다.
            if response.status_code == 404:
                return response
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt + 1 < retries:
                await asyncio.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"공식 설명서 요청 실패: {url}") from last_error


async def match_lg_manuals(
    client: httpx.AsyncClient,
    model: CatalogModel,
) -> ManualMatchResult:
    """LG 공개 AJAX가 정확한 모델 코드로 반환한 문서만 연결합니다."""

    response = await _request_with_retry(
        client,
        "GET",
        LG_MANUAL_API,
        params={"modelCode": model.model_name},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.lge.co.kr/support/product-manuals",
        },
    )
    payload = response.json()
    items = payload.get("data", {}).get("manual", {}).get("listData", [])
    documents: list[ManualDocumentCandidate] = []
    for item in items if isinstance(items, list) else []:
        sales_model = str(item.get("salesModelCd") or "")
        if normalize_model_name(sales_model) != normalize_model_name(model.model_name):
            continue
        files = item.get("file") if isinstance(item.get("file"), list) else []
        # 구조화 단계에서 읽기 쉬운 HTML을 우선하고 없으면 PDF를 선택합니다.
        ranked_files = sorted(
            files,
            key=lambda value: (
                0 if str(value.get("type", "")).lower() == "html" else 1,
                0 if str(value.get("type", "")).lower() == "pdf" else 1,
            ),
        )
        if not ranked_files:
            continue
        chosen = ranked_files[0]
        source_url = str(chosen.get("src") or "")
        if not source_url:
            continue
        file_id = str(item.get("fileId") or source_url)
        document_key = hashlib.sha256(f"lg|{file_id}".encode()).hexdigest()
        documents.append(
            ManualDocumentCandidate(
                document_key=document_key,
                source_url=source_url.replace("http://", "https://", 1),
                title=f"{item.get('type') or '사용설명서'}: {item.get('title') or ''}".strip(),
                language=str(item.get("language") or "") or None,
                media_type=_media_type(str(chosen.get("type") or ""), source_url),
                model_scope_text=sales_model,
                matching_method="lg_official_exact_model_api",
                raw_metadata={
                    "provider": "LG전자",
                    "file_id": item.get("fileId"),
                    "manual_code": item.get("manualCode"),
                    "date": item.get("date"),
                    "alternate_files": files,
                },
            )
        )
    status = "matched" if documents else "not_found"
    return ManualMatchResult(model.id, "lg", status, tuple(documents), f"documents={len(documents)}")


def _strip_tags(value: str) -> str:
    """삼성 응답의 짧은 표시 문구에서 HTML 태그와 연속 공백을 제거합니다."""

    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?is)<[^>]+>", " ", value))).strip()


def parse_samsung_manual_html(
    manual_html: str,
    *,
    model_name: str,
    product_url: str,
) -> tuple[ManualDocumentCandidate, ...]:
    """삼성 공식 AJAX HTML에서 설명서 링크와 표시 메타데이터를 읽습니다."""

    documents: list[ManualDocumentCandidate] = []
    item_pattern = re.compile(r"(?is)<li\s+class=[\"']item[\"']([^>]*)>(.*?)</li>")
    for attributes, body in item_pattern.findall(manual_html):
        name_match = re.search(
            r"(?is)<strong\s+class=[\"']name[\"'][^>]*>(.*?)</strong>", body
        )
        title = _strip_tags(name_match.group(1)) if name_match else "삼성 사용자 매뉴얼"
        url_match = re.search(
            r"(?is)(?:href|data-url)=[\"'](https?://[^\"']+)[\"'][^>]*"
            r"class=[\"'][^\"']*btn-download",
            body,
        )
        if url_match is None:
            # 속성 순서가 반대인 공식 HTML도 읽도록 다운로드 클래스 뒤 URL을 한 번 더 찾습니다.
            url_match = re.search(
                r"(?is)class=[\"'][^\"']*btn-download[^\"']*[\"'][^>]*"
                r"(?:href|data-url)=[\"'](https?://[^\"']+)[\"']",
                body,
            )
        if url_match is None:
            continue
        source_url = html.unescape(url_match.group(1))
        content_id_match = re.search(r"data-omni\s*=\s*[\"']?([^\"'\s>]+)", attributes)
        content_id = content_id_match.group(1) if content_id_match else source_url
        descriptions = [
            _strip_tags(value)
            for value in re.findall(
                r"(?is)<span\s+class=[\"']desc-item[\"'][^>]*>(.*?)</span>", body
            )
        ]
        documents.append(
            ManualDocumentCandidate(
                document_key=hashlib.sha256(f"samsung|{content_id}|{source_url}".encode()).hexdigest(),
                source_url=source_url,
                title=title,
                language=next((value for value in descriptions if "어" in value), None),
                media_type=_media_type("", source_url),
                model_scope_text=model_name,
                matching_method="samsung_official_exact_model_page",
                raw_metadata={
                    "provider": "삼성전자",
                    "content_id": content_id,
                    "descriptions": descriptions,
                    "product_url": product_url,
                },
            )
        )
    return tuple(documents)


def parse_qaid_manual_html(page: str) -> list[ManualDocumentCandidate]:
    """큐에이드 가정용 세탁기 목록에서 모델 코드와 같은 행의 문서를 읽습니다."""

    documents = []
    for row in re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", page):
        model = re.search(r'\bdata-model="([^"]+)"', row)
        file = re.search(r"fnFileDownloadAjax\('(F\d+)'\s*,\s*'(\d+)'\)", row)
        if model is None or file is None:
            continue
        model_name = html.unescape(model.group(1)).strip()
        file_id, file_seq = file.groups()
        url = f"{QAID_DOWNLOAD}?{urlencode({'fileId': file_id, 'fileSeq': file_seq})}"
        documents.append(ManualDocumentCandidate(
            document_key=hashlib.sha256(f"qaid|{file_id}|{file_seq}".encode()).hexdigest(),
            source_url=url,
            title="제품 사용설명서",
            language="ko",
            media_type=None,
            model_scope_text=model_name,
            matching_method="qaid_official_exact_model_index",
            raw_metadata={"provider": "큐에이드", "list_url": QAID_MANUAL_LIST},
        ))
    return documents


async def load_qaid_manual_index(
    client: httpx.AsyncClient, concurrency: int,
) -> dict[str, tuple[ManualDocumentCandidate, ...]]:
    """공식 세탁기 목록을 페이지 단위로 읽고 모델명 검색에 재사용합니다."""

    async def fetch_page(page: int) -> httpx.Response:
        return await _request_with_retry(
            client, "GET", QAID_MANUAL_LIST,
            params={"categoryCode": QAID_WASHER_CATEGORY, "pageIndex": page},
        )

    first = await fetch_page(1)
    count = re.search(r"전체\s*(?:<[^>]+>\s*)*([0-9,]+)(?:\s*</[^>]+>)*\s*건", first.text)
    documents = parse_qaid_manual_html(first.text)
    if not count or not documents:
        raise RuntimeError("큐에이드 세탁기 설명서 목록을 확인하지 못했습니다.")
    total = int(count.group(1).replace(",", ""))
    page_size = len(documents)
    page_count = ceil(total / page_size)
    for start in range(2, page_count + 1, concurrency):
        pages = await asyncio.gather(*(fetch_page(page) for page in range(
            start, min(start + concurrency, page_count + 1),
        )))
        for response in pages:
            documents.extend(parse_qaid_manual_html(response.text))
    if len(documents) != total:
        raise RuntimeError("큐에이드 세탁기 설명서 목록의 전체 건수가 일치하지 않습니다.")
    indexed: dict[str, dict[str, ManualDocumentCandidate]] = {}
    for document in documents:
        model_name = normalize_model_name(document.model_scope_text or "")
        indexed.setdefault(model_name, {})[document.document_key] = document
    return {model_name: tuple(items.values()) for model_name, items in indexed.items()}


async def match_samsung_manuals(
    client: httpx.AsyncClient,
    model: CatalogModel,
) -> ManualMatchResult:
    """삼성 정확 모델 지원 페이지와 공식 AJAX를 차례로 확인합니다."""

    product_url = SAMSUNG_MODEL_URL.format(model_name=model.model_name)
    page_response = await _request_with_retry(client, "GET", product_url)
    if page_response.status_code == 404:
        return ManualMatchResult(model.id, "samsung", "not_found", note="product_page_404")
    page_html = page_response.text
    model_match = re.search(r'mdlCode\s*:\s*["\']([^"\']+)', page_html)
    goods_match = re.search(r'goodsId\s*:\s*["\']([^"\']+)', page_html)
    if model_match is None or goods_match is None:
        return ManualMatchResult(model.id, "samsung", "not_found", note="model_metadata_missing")
    official_model = model_match.group(1)
    if normalize_model_name(official_model) != normalize_model_name(model.model_name):
        return ManualMatchResult(model.id, "samsung", "not_found", note="exact_model_mismatch")
    manual_response = await _request_with_retry(
        client,
        "POST",
        SAMSUNG_MANUAL_API,
        data={
            "mdlCode": official_model,
            "goodsId": goods_match.group(1),
            "manualLang": "KO",
            "mdlNm": official_model,
            "supportYn": "Y",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": product_url},
    )
    documents = parse_samsung_manual_html(
        manual_response.text,
        model_name=official_model,
        product_url=product_url,
    )
    status = "matched" if documents else "not_found"
    return ManualMatchResult(
        model.id,
        "samsung",
        status,
        documents,
        f"documents={len(documents)}",
    )


async def _match_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    model: CatalogModel,
    adapter: str,
) -> ManualMatchResult:
    """동시 요청 수를 제한하고 모델별 오류를 재시도 큐 상태로 격리합니다."""

    async with semaphore:
        try:
            if adapter == "lg":
                return await match_lg_manuals(client, model)
            return await match_samsung_manuals(client, model)
        except (httpx.HTTPError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return ManualMatchResult(
                model.id,
                adapter,
                "error_retry",
                note=f"{type(exc).__name__}: {exc}",
            )


def _store_results(db: Session, models_by_id: dict[str, CatalogModel], results: list[ManualMatchResult]) -> None:
    """공식 문서와 정확 모델 연결을 반복 실행에서도 한 번만 저장합니다."""

    documents_by_key = {
        document.document_key: document for document in db.scalars(select(CatalogDocument)).all()
    }
    existing_links = set(
        db.execute(
            select(CatalogModelDocument.catalog_model_id, CatalogModelDocument.document_id)
        ).all()
    )
    checked_at = utc_now()
    for result in results:
        model = models_by_id[result.model_id]
        model.manual_match_status = result.status
        model.manual_checked_at = checked_at
        model.manual_match_notes = f"adapter={result.adapter}; {result.note or ''}".strip()
        for candidate in result.documents:
            document = documents_by_key.get(candidate.document_key)
            if document is None:
                document = CatalogDocument(
                    id=new_id(),
                    document_key=candidate.document_key,
                    source_url=candidate.source_url,
                    title=candidate.title,
                    language=candidate.language,
                    media_type=candidate.media_type,
                    retrieval_status="metadata_only",
                    extraction_status="pending",
                    model_scope_text=candidate.model_scope_text,
                    raw_metadata=candidate.raw_metadata,
                )
                db.add(document)
                documents_by_key[candidate.document_key] = document
            link_key = (model.id, document.id)
            if link_key not in existing_links:
                db.add(
                    CatalogModelDocument(
                        id=new_id(),
                        catalog_model_id=model.id,
                        document_id=document.id,
                        matching_method=candidate.matching_method,
                        matching_status="confirmed",
                        exact_model_match=True,
                        evidence=f"공식 고객지원의 적용 모델명 {candidate.model_scope_text or model.model_name}",
                    )
                )
                existing_links.add(link_key)
    db.commit()


def _write_progress(path: Path, models: list[CatalogModel]) -> dict[str, int]:
    """50% 알림과 재개 판단에 사용할 모델별 설명서 상태 건수를 저장합니다."""

    counts: dict[str, int] = {}
    for model in models:
        counts[model.manual_match_status] = counts.get(model.manual_match_status, 0) + 1
    payload = {
        "scope": "KR official washer manual matching",
        "updated_at": utc_now().isoformat(),
        "total_models": len(models),
        "status_counts": counts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


async def _run_network_batches(
    db: Session,
    models: list[CatalogModel],
    *,
    concurrency: int,
    batch_size: int,
    progress_file: Path,
) -> None:
    """작은 배치마다 공식 조회 결과를 커밋해 중단 후 재개 시간을 줄입니다."""

    semaphore = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    headers = {"User-Agent": "WashWiseManualCollector/0.1"}
    models_by_id = {model.id: model for model in models}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        limits=limits,
        headers=headers,
    ) as client:
        supported = [(model, select_adapter(model)) for model in models]
        # 어댑터가 없는 업체도 미확인 상태를 명시해 전체 시도 분모에서 숨기지 않습니다.
        unsupported_results = [
            ManualMatchResult(
                model.id,
                None,
                "unsupported_official_source",
                note="공식 자동조회 어댑터 미구현",
            )
            for model, adapter in supported
            if adapter is None
        ]
        for start in range(0, len(unsupported_results), batch_size):
            _store_results(db, models_by_id, unsupported_results[start : start + batch_size])
            counts = _write_progress(progress_file, models)
            print(
                json.dumps(
                    {"stage": "manual_matching", "total": len(models), "status_counts": counts},
                    ensure_ascii=False,
                ),
                flush=True,
            )
        qaid_models = [model for model, adapter in supported if adapter == "qaid"]
        if qaid_models:
            try:
                index = await load_qaid_manual_index(client, concurrency)
            except (RuntimeError, httpx.HTTPError) as exc:
                qaid_results = [
                    ManualMatchResult(model.id, "qaid", "error_retry", note=str(exc))
                    for model in qaid_models
                ]
            else:
                qaid_results = []
                for model in qaid_models:
                    documents = index.get(normalize_model_name(model.model_name), ())
                    status = "matched" if documents else "not_found"
                    qaid_results.append(ManualMatchResult(model.id, "qaid", status, documents))
            for start in range(0, len(qaid_results), batch_size):
                _store_results(db, models_by_id, qaid_results[start : start + batch_size])
                _write_progress(progress_file, models)
        network_targets = [(model, adapter) for model, adapter in supported if adapter in {"lg", "samsung"}]
        for start in range(0, len(network_targets), batch_size):
            batch = network_targets[start : start + batch_size]
            tasks = [_match_one(client, semaphore, model, adapter) for model, adapter in batch]
            results = list(await asyncio.gather(*tasks))
            _store_results(db, models_by_id, results)
            counts = _write_progress(progress_file, models)
            print(
                json.dumps(
                    {"stage": "manual_matching", "total": len(models), "status_counts": counts},
                    ensure_ascii=False,
                ),
                flush=True,
            )


def run_matching(
    *,
    concurrency: int,
    batch_size: int,
    limit: int | None,
    retry_errors: bool,
    progress_file: Path,
    retry_unmatched: bool = False,
    provider: str | None = None,
) -> dict[str, int]:
    """pending 모델과 선택적인 오류 재시도 모델을 공식 사이트에서 조회합니다."""

    db = SessionLocal()
    try:
        statuses = ["pending"]
        if retry_errors:
            statuses.append("error_retry")
        if retry_unmatched:
            statuses.extend(["not_found", "unsupported_official_source"])
        statement = (
            select(CatalogModel)
            .where(CatalogModel.manual_match_status.in_(statuses))
            .order_by(CatalogModel.id)
        )
        models = list(db.scalars(statement).all())
        if provider is not None:
            models = [model for model in models if select_adapter(model) == provider]
        if limit is not None:
            models = models[:limit]
        if models:
            asyncio.run(
                _run_network_batches(
                    db,
                    models,
                    concurrency=concurrency,
                    batch_size=batch_size,
                    progress_file=progress_file,
                )
            )
        all_models = list(db.scalars(select(CatalogModel)).all())
        return _write_progress(progress_file, all_models)
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    """공식 사이트 부하와 재시도 범위를 명령행에서 조절합니다."""

    parser = argparse.ArgumentParser(description="한국 내수 세탁기 공식 설명서 매칭")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--retry-unmatched", action="store_true")
    parser.add_argument("--provider", choices=("lg", "samsung", "qaid"))
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=Path(".tmp/manual-progress.json"),
    )
    return parser


def main() -> int:
    """공식 설명서 매칭을 실행하고 모델 상태별 건수를 출력합니다."""

    args = build_parser().parse_args()
    if args.concurrency < 1 or args.concurrency > 10:
        raise SystemExit("--concurrency는 1~10 사이여야 합니다.")
    if args.batch_size < 1 or args.batch_size > 500:
        raise SystemExit("--batch-size는 1~500 사이여야 합니다.")
    counts = run_matching(
        concurrency=args.concurrency,
        batch_size=args.batch_size,
        limit=args.limit,
        retry_errors=args.retry_errors,
        progress_file=args.progress_file,
        retry_unmatched=args.retry_unmatched,
        provider=args.provider,
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


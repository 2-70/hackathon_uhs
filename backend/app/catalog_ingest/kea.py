"""한국에너지공단의 한국 내수 세탁기 신고 목록을 수집합니다."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    CatalogIngestionRun,
    CatalogModel,
    CatalogSource,
    CatalogSourceRecord,
    new_id,
    utc_now,
)
from backend.app.db.session import SessionLocal

# 사용자가 확정한 최근 15년의 양 끝 날짜를 실행일과 무관하게 고정합니다.
PERIOD_START = date(2011, 11, 11)
PERIOD_END = date(2026, 11, 11)


@dataclass(frozen=True)
class KeaSourceSpec:
    """KEA 자료원 한 개의 주소와 분류 규칙입니다."""

    source_key: str
    name: str
    category: str
    machine_family: str
    export_url: str
    list_url: str
    reported_count: int


# 현행 기준과 2017년 이전 구기자재를 모두 읽어 기간 공백을 줄입니다.
KEA_SOURCES = (
    KeaSourceSpec(
        source_key="kea-kr-current-general",
        name="한국에너지공단 전기세탁기(일반) 현행 목록",
        category="current_general_washer",
        machine_family="general_washer",
        export_url=(
            "https://eep.energy.or.kr/certification/"
            "certi_excel_298.aspx?searchfield=&searchword="
        ),
        list_url="https://eep.energy.or.kr/certification/certi_list_298.aspx",
        reported_count=761,
    ),
    KeaSourceSpec(
        source_key="kea-kr-current-drum",
        name="한국에너지공단 전기세탁기(드럼) 현행 목록",
        category="current_drum_washer",
        machine_family="drum_washer",
        export_url=(
            "https://eep.energy.or.kr/certification/"
            "certi_excel_299.aspx?searchfield=&searchword="
        ),
        list_url="https://eep.energy.or.kr/certification/certi_list_299.aspx",
        reported_count=1032,
    ),
    KeaSourceSpec(
        source_key="kea-kr-legacy-general",
        name="한국에너지공단 전기세탁기(일반) 구기자재 목록",
        category="legacy_general_washer",
        machine_family="general_washer",
        export_url=(
            "https://eep.energy.or.kr/certification/"
            "certi_excel_103.aspx?searchfield=&searchword="
        ),
        list_url="https://eep.energy.or.kr/certification/certi_list_103.aspx",
        reported_count=1653,
    ),
    KeaSourceSpec(
        source_key="kea-kr-legacy-drum",
        name="한국에너지공단 전기세탁기(드럼) 구기자재 목록",
        category="legacy_drum_washer",
        machine_family="drum_washer",
        export_url=(
            "https://eep.energy.or.kr/certification/"
            "certi_excel_118.aspx?searchfield=&searchword="
        ),
        list_url="https://eep.energy.or.kr/certification/certi_list_118.aspx",
        reported_count=1599,
    ),
)


@dataclass(frozen=True)
class KeaRecord:
    """공식 엑셀 HTML의 한 행을 의미가 있는 필드로 바꾼 값입니다."""

    row_number: int | None
    applicant_name: str | None
    completed_on: date | None
    completed_on_raw: str
    model_name: str
    test_agency: str | None
    manufacturer_name: str | None
    origin_claim: str | None
    capacity_kg: float | None
    efficiency_grade: str | None
    raw_data: dict[str, str]
    # 원문이 완전히 같은 중복 행도 각각 보존하기 위한 파일 내 순번입니다.
    content_ordinal: int


@dataclass
class SourceSummary:
    """자료원별 수집 결과를 비밀정보 없이 출력하기 위한 통계입니다."""

    source_key: str
    fetched_count: int = 0
    included_count: int = 0
    excluded_count: int = 0
    uncertain_date_count: int = 0
    distinct_model_count: int = 0
    duplicate_count: int = 0
    raw_sha256: str | None = None
    elapsed_seconds: float = 0.0
    status: str = "pending"
    error: str | None = None


class HtmlTableParser(HTMLParser):
    """추가 패키지 없이 KEA의 HTML 형식 엑셀 표를 읽습니다."""

    def __init__(self) -> None:
        # HTML 엔티티는 표 셀의 실제 문자로 자동 변환합니다.
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """행과 셀 시작 위치를 기록합니다."""

        del attrs
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell_parts = []
        elif tag.lower() == "br" and self._cell_parts is not None:
            self._cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        """현재 셀 안의 텍스트를 순서대로 모읍니다."""

        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        """셀 텍스트를 정리하고 완성된 행을 목록에 넣습니다."""

        lowered = tag.lower()
        if lowered in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            self._row.append(clean_text("".join(self._cell_parts)))
            self._cell_parts = None
        elif lowered == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def clean_text(value: str) -> str:
    """줄바꿈과 연속 공백만 정리하고 원문의 기호는 보존합니다."""

    return re.sub(r"\s+", " ", value).strip()


def clean_optional(value: str | None) -> str | None:
    """빈 값과 공식 구기자재 파일의 깨진 물음표 값은 미확인으로 바꿉니다."""

    cleaned = clean_text(value or "")
    if not cleaned:
        return None
    # 글자 정보가 하나도 없고 물음표·괄호·공백뿐이면 제조사를 추정하지 않습니다.
    if re.fullmatch(r"[?？()（）\s.,·-]+", cleaned):
        return None
    return cleaned


def normalize_model_name(value: str) -> str:
    """정확한 원문은 유지하면서 중복 비교용 모델명만 정규화합니다."""

    normalized = unicodedata.normalize("NFKC", clean_text(value)).upper()
    # 모델 코드 안의 표시상 공백 차이만 제거하고 하이픈·접미사는 그대로 둡니다.
    return re.sub(r"\s+", "", normalized)


def make_catalog_key(machine_family: str, model_name: str) -> str:
    """긴 모델명도 자르지 않는 안정적인 한국시장 모델 키를 만듭니다."""

    identity = f"KR|{machine_family}|{normalize_model_name(model_name)}"
    return f"kr-kea-{machine_family}-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"


def parse_optional_date(value: str) -> date | None:
    """공식 완료일자의 고정 형식만 날짜로 허용합니다."""

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_optional_float(value: str | None) -> float | None:
    """용량 숫자만 읽고 단위나 미확인 값은 추정하지 않습니다."""

    cleaned = clean_text(value or "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _column_value(row: dict[str, str], *needles: str) -> str:
    """현행·구기자재 사이의 작은 열 이름 차이를 안전하게 흡수합니다."""

    for header, value in row.items():
        compact_header = re.sub(r"\s+", "", header)
        if any(needle in compact_header for needle in needles):
            return value
    return ""


def parse_kea_export(raw: bytes) -> list[KeaRecord]:
    """KEA의 CP949 HTML 엑셀 응답을 원본 행 목록으로 변환합니다."""

    # 공식 응답 헤더가 지정한 ks_c_5601 계열을 Windows 확장 문자까지 읽습니다.
    html = raw.decode("cp949", errors="replace")
    parser = HtmlTableParser()
    parser.feed(html)
    # 첫 행은 문서 제목이고, 두 번째 행이 실제 열 이름입니다.
    if len(parser.rows) < 3:
        raise ValueError("KEA 엑셀 표에서 제목·헤더·데이터 행을 찾지 못했습니다.")
    headers = parser.rows[1]
    records: list[KeaRecord] = []
    content_occurrences: dict[str, int] = {}
    for cells in parser.rows[2:]:
        # 열 수가 맞지 않는 행은 잘못 연결하지 않고 수집 오류로 즉시 알립니다.
        if len(cells) != len(headers):
            raise ValueError(
                f"KEA 엑셀 행의 열 수가 다릅니다: expected={len(headers)}, actual={len(cells)}"
            )
        raw_data = dict(zip(headers, cells, strict=True))
        row_number_text = _column_value(raw_data, "번호")
        model_name = clean_text(_column_value(raw_data, "모델명"))
        if not model_name:
            raise ValueError("KEA 엑셀 데이터 행에 모델명이 없습니다.")
        completed_raw = clean_text(_column_value(raw_data, "완료일자"))
        capacity_raw = _column_value(raw_data, "표준세탁용량")
        raw_content_hash = hashlib.sha256(
            json.dumps(raw_data, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        content_occurrences[raw_content_hash] = content_occurrences.get(raw_content_hash, 0) + 1
        records.append(
            KeaRecord(
                row_number=int(row_number_text) if row_number_text.isdigit() else None,
                applicant_name=clean_optional(_column_value(raw_data, "업체명")),
                completed_on=parse_optional_date(completed_raw),
                completed_on_raw=completed_raw,
                model_name=model_name,
                test_agency=clean_optional(_column_value(raw_data, "시험기관")),
                manufacturer_name=clean_optional(_column_value(raw_data, "제조원")),
                origin_claim=clean_optional(_column_value(raw_data, "국산/수입")),
                capacity_kg=parse_optional_float(capacity_raw),
                efficiency_grade=clean_optional(_column_value(raw_data, "효율등급")),
                raw_data=raw_data,
                content_ordinal=content_occurrences[raw_content_hash],
            )
        )
    return records


def classify_record(record: KeaRecord) -> tuple[str, str]:
    """등록 완료일을 판매일로 바꾸지 않고 기간 포함 상태만 판정합니다."""

    if record.completed_on is None:
        return "candidate", "registration_date_uncertain"
    if record.completed_on < PERIOD_START:
        return "excluded", "registration_completed_before_period"
    if record.completed_on > PERIOD_END:
        return "excluded", "registration_completed_after_period"
    return "candidate", "official_kr_registration_in_period"


def make_source_record_key(record: KeaRecord) -> str:
    """행 순서가 바뀌어도 같은 원문 행과 동일 중복 순번을 찾는 키를 만듭니다."""

    # 일부 신고 행은 모델·날짜가 같아도 에너지 지표가 다르므로 전체 원문 해시를 씁니다.
    identity = {"content_sha256": make_content_hash(record), "ordinal": record.content_ordinal}
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def make_content_hash(record: KeaRecord) -> str:
    """원본 열 값이 바뀌었는지 비교할 해시를 만듭니다."""

    encoded = json.dumps(record.raw_data, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def fetch_export(spec: KeaSourceSpec, retries: int = 3) -> bytes:
    """공식 엑셀을 제한된 재시도와 지수 백오프로 다운로드합니다."""

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            # 고정 User-Agent는 운영자가 공단 로그에서 수집기를 식별할 수 있게 합니다.
            with httpx.Client(
                timeout=httpx.Timeout(60.0),
                follow_redirects=True,
                headers={"User-Agent": "WashWiseCatalogCollector/0.1"},
            ) as client:
                response = client.get(spec.export_url)
                response.raise_for_status()
            if not response.content:
                raise ValueError("KEA 엑셀 응답이 비어 있습니다.")
            return response.content
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"KEA 자료원 다운로드 실패: {spec.source_key}") from last_error


def summarize_records(spec: KeaSourceSpec, raw: bytes, elapsed: float) -> tuple[list[KeaRecord], SourceSummary]:
    """다운로드 원본을 파싱하고 DB 저장 전 통계를 계산합니다."""

    records = parse_kea_export(raw)
    included_keys: list[str] = []
    summary = SourceSummary(
        source_key=spec.source_key,
        fetched_count=len(records),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        elapsed_seconds=round(elapsed, 3),
        status="parsed",
    )
    for record in records:
        eligibility, reason = classify_record(record)
        if eligibility == "excluded":
            summary.excluded_count += 1
            continue
        summary.included_count += 1
        if reason == "registration_date_uncertain":
            summary.uncertain_date_count += 1
        included_keys.append(make_catalog_key(spec.machine_family, record.model_name))
    summary.distinct_model_count = len(set(included_keys))
    summary.duplicate_count = len(included_keys) - summary.distinct_model_count
    return records, summary


def _ensure_source(db: Session, spec: KeaSourceSpec, checked_at: datetime) -> CatalogSource:
    """자료원 메타데이터를 반복 실행에서도 한 행으로 유지합니다."""

    source = db.scalar(select(CatalogSource).where(CatalogSource.source_key == spec.source_key))
    if source is None:
        source = CatalogSource(
            id=new_id(),
            source_key=spec.source_key,
            name=spec.name,
            authority="한국에너지공단",
            country_code="KR",
            category=spec.category,
            source_url=spec.list_url,
            reported_count=spec.reported_count,
            last_checked_at=checked_at,
        )
        db.add(source)
    else:
        source.name = spec.name
        source.category = spec.category
        source.source_url = spec.list_url
        source.reported_count = spec.reported_count
        source.last_checked_at = checked_at
    db.flush()
    return source


def _newest_record_wins(model: CatalogModel, record: KeaRecord) -> bool:
    """오래된 구기자재가 더 최근의 표시 정보를 덮어쓰지 않게 합니다."""

    if model.latest_registration_completed_on is None:
        return record.completed_on is not None
    return record.completed_on is not None and record.completed_on >= model.latest_registration_completed_on


def ingest_records(
    db: Session,
    spec: KeaSourceSpec,
    records: list[KeaRecord],
    summary: SourceSummary,
) -> SourceSummary:
    """한 자료원을 한 트랜잭션으로 upsert해 중단 시 부분 행을 남기지 않습니다."""

    now = utc_now()
    source = _ensure_source(db, spec, now)
    run = CatalogIngestionRun(
        id=new_id(),
        source_id=source.id,
        status="running",
        checkpoint={"stage": "upserting", "source_key": spec.source_key},
        started_at=now,
        fetched_count=summary.fetched_count,
        included_count=summary.included_count,
        excluded_count=summary.excluded_count,
        model_count=summary.distinct_model_count,
        duplicate_count=summary.duplicate_count,
        error_count=0,
        raw_sha256=summary.raw_sha256,
    )
    db.add(run)
    # 전체 모델을 한 번에 읽어 행마다 원격 DB를 조회하는 N+1 문제를 피합니다.
    models_by_key = {
        model.catalog_key: model for model in db.scalars(select(CatalogModel)).all()
    }
    records_by_key = {
        item.source_record_key: item
        for item in db.scalars(
            select(CatalogSourceRecord).where(CatalogSourceRecord.source_id == source.id)
        ).all()
    }
    # 이전 수집기 키로 저장된 행은 같은 원문 해시를 찾으면 새 키로 안전하게 이동합니다.
    records_by_content: dict[str, list[CatalogSourceRecord]] = {}
    for existing_record in records_by_key.values():
        records_by_content.setdefault(existing_record.content_sha256, []).append(existing_record)
    migrated_record_ids: set[str] = set()
    for record in records:
        eligibility, reason = classify_record(record)
        catalog_model: CatalogModel | None = None
        if eligibility != "excluded":
            catalog_key = make_catalog_key(spec.machine_family, record.model_name)
            catalog_model = models_by_key.get(catalog_key)
            if catalog_model is None:
                catalog_model = CatalogModel(
                    id=new_id(),
                    catalog_key=catalog_key,
                    machine_family=spec.machine_family,
                    use_type="household",
                    market_region="KR",
                    model_name=record.model_name,
                    normalized_model_name=normalize_model_name(record.model_name),
                    applicant_name=record.applicant_name,
                    manufacturer_name=record.manufacturer_name,
                    origin_claim=record.origin_claim,
                    capacity_kg=record.capacity_kg,
                    latest_registration_completed_on=record.completed_on,
                    market_status="candidate",
                    evidence_status=(
                        "date_uncertain"
                        if record.completed_on is None
                        else "market_evidence_only"
                    ),
                    recommendation_status="catalog_only",
                    source_url=spec.list_url,
                )
                db.add(catalog_model)
                models_by_key[catalog_key] = catalog_model
            elif _newest_record_wins(catalog_model, record):
                # 최신 신고 행의 표시정보만 갱신하고 기존의 비어 있지 않은 값은 보존합니다.
                catalog_model.model_name = record.model_name
                catalog_model.applicant_name = record.applicant_name or catalog_model.applicant_name
                catalog_model.manufacturer_name = (
                    record.manufacturer_name or catalog_model.manufacturer_name
                )
                catalog_model.origin_claim = record.origin_claim or catalog_model.origin_claim
                catalog_model.capacity_kg = record.capacity_kg or catalog_model.capacity_kg
                catalog_model.latest_registration_completed_on = record.completed_on
                catalog_model.source_url = spec.list_url
        source_record_key = make_source_record_key(record)
        content_hash = make_content_hash(record)
        stored = records_by_key.get(source_record_key)
        if stored is None:
            legacy_candidates = records_by_content.get(content_hash, [])
            stored = next(
                (item for item in legacy_candidates if item.id not in migrated_record_ids),
                None,
            )
            if stored is not None:
                # 기존 행 ID와 최초 발견시각을 보존하면서 새 안정 키만 적용합니다.
                stored.source_record_key = source_record_key
                records_by_key[source_record_key] = stored
                migrated_record_ids.add(stored.id)
        if stored is None:
            stored = CatalogSourceRecord(
                id=new_id(),
                source_id=source.id,
                catalog_model_id=catalog_model.id if catalog_model else None,
                source_record_key=source_record_key,
                source_row_number=record.row_number,
                completed_on=record.completed_on,
                model_name_raw=record.model_name,
                applicant_name_raw=record.applicant_name,
                manufacturer_name_raw=record.manufacturer_name,
                origin_claim_raw=record.origin_claim,
                capacity_kg=record.capacity_kg,
                efficiency_grade_raw=record.efficiency_grade,
                eligibility_status=eligibility,
                eligibility_reason=reason,
                raw_data=record.raw_data,
                content_sha256=content_hash,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(stored)
            records_by_key[source_record_key] = stored
        else:
            stored.catalog_model_id = catalog_model.id if catalog_model else None
            stored.source_row_number = record.row_number
            stored.completed_on = record.completed_on
            stored.eligibility_status = eligibility
            stored.eligibility_reason = reason
            stored.raw_data = record.raw_data
            stored.content_sha256 = content_hash
            stored.last_seen_at = now
    run.status = "completed"
    run.checkpoint = {"stage": "completed", "source_key": spec.source_key}
    run.finished_at = utc_now()
    db.commit()
    summary.status = "stored"
    return summary


def _source_already_completed(db: Session, spec: KeaSourceSpec) -> bool:
    """--resume에서 완료된 자료원을 건너뛸지 확인합니다."""

    source = db.scalar(select(CatalogSource).where(CatalogSource.source_key == spec.source_key))
    if source is None:
        return False
    completed = db.scalar(
        select(CatalogIngestionRun.id)
        .where(
            CatalogIngestionRun.source_id == source.id,
            CatalogIngestionRun.status == "completed",
        )
        .order_by(CatalogIngestionRun.started_at.desc())
        .limit(1)
    )
    return completed is not None


def write_progress(
    path: Path,
    summaries: list[SourceSummary],
    overall_distinct_model_count: int,
) -> None:
    """중단 후에도 확인할 수 있는 비밀정보 없는 진행 상태를 저장합니다."""

    path.parent.mkdir(parents=True, exist_ok=True)
    included_keys = sum(item.distinct_model_count for item in summaries)
    payload = {
        "scope": "KR domestic market washer candidates",
        "period": {"start": PERIOD_START.isoformat(), "end": PERIOD_END.isoformat()},
        "updated_at": utc_now().isoformat(),
        "source_count": len(KEA_SOURCES),
        "processed_source_count": len([item for item in summaries if item.status != "pending"]),
        "overall_distinct_candidate_models": overall_distinct_model_count,
        "sum_source_distinct_models_before_cross_source_dedup": included_keys,
        "sources": [asdict(item) for item in summaries],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def collect(
    *,
    commit: bool,
    resume: bool,
    selected_keys: set[str] | None,
    progress_file: Path,
) -> list[SourceSummary]:
    """선택된 공식 자료원을 순서대로 수집하고 자료원 단위로 체크포인트를 남깁니다."""

    specs = [
        spec for spec in KEA_SOURCES if selected_keys is None or spec.source_key in selected_keys
    ]
    summaries: list[SourceSummary] = []
    # 자료원 사이에 같은 모델이 다시 등장하므로 전체 스냅샷 키를 따로 합칩니다.
    overall_model_keys: set[str] = set()
    db = SessionLocal() if commit else None
    try:
        for spec in specs:
            if db is not None and resume and _source_already_completed(db, spec):
                summaries.append(SourceSummary(source_key=spec.source_key, status="skipped_completed"))
                write_progress(progress_file, summaries, len(overall_model_keys))
                continue
            started = time.perf_counter()
            try:
                raw = fetch_export(spec)
                elapsed = time.perf_counter() - started
                records, summary = summarize_records(spec, raw, elapsed)
                overall_model_keys.update(
                    make_catalog_key(spec.machine_family, record.model_name)
                    for record in records
                    if classify_record(record)[0] != "excluded"
                )
                if db is not None:
                    ingest_records(db, spec, records, summary)
                else:
                    summary.status = "dry_run"
                summaries.append(summary)
            except (httpx.HTTPError, OSError, RuntimeError, SQLAlchemyError, ValueError) as exc:
                if db is not None:
                    db.rollback()
                summaries.append(
                    SourceSummary(
                        source_key=spec.source_key,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}",
                        elapsed_seconds=round(time.perf_counter() - started, 3),
                    )
                )
            write_progress(progress_file, summaries, len(overall_model_keys))
    finally:
        if db is not None:
            db.close()
    return summaries


def build_parser() -> argparse.ArgumentParser:
    """실수로 운영 DB에 쓰지 않도록 기본 동작을 dry-run으로 둡니다."""

    parser = argparse.ArgumentParser(description="한국에너지공단 세탁기 목록 수집기")
    parser.add_argument("--commit", action="store_true", help="현재 DATABASE_URL에 실제 저장")
    parser.add_argument("--resume", action="store_true", help="완료된 자료원을 건너뛰고 재개")
    parser.add_argument(
        "--source",
        action="append",
        choices=[spec.source_key for spec in KEA_SOURCES],
        help="특정 자료원만 처리하며 여러 번 지정 가능",
    )
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=Path(".tmp/catalog-progress.json"),
        help="비밀정보 없는 진행 상태 JSON 경로",
    )
    return parser


def main() -> int:
    """명령행 수집을 실행하고 기계가 읽을 수 있는 JSON 통계를 출력합니다."""

    args = build_parser().parse_args()
    summaries = collect(
        commit=args.commit,
        resume=args.resume,
        selected_keys=set(args.source) if args.source else None,
        progress_file=args.progress_file,
    )
    print(json.dumps([asdict(item) for item in summaries], ensure_ascii=False, indent=2))
    return 1 if any(item.status == "failed" for item in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())

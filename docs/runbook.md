# WashWise 실행·검증 Runbook

## 핵심 개념

서버는 시작할 때 테이블을 자동 생성하지 않습니다. 먼저 Alembic migration을 적용하고, 그다음 Uvicorn을 실행합니다. 앱 연결은 API 서버 주소만 사용하며 Neon URL과 AI 키는 모바일에 넣지 않습니다.

## 1. 로컬 SQLite

```powershell
uv sync --extra dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run python -m backend.seed.load_verified --washwise-demo
uv run uvicorn backend.app.main:app --reload
```

`.env`의 `DATABASE_URL=sqlite:///./washwise.db`를 사용합니다. AI 경로까지 확인하려면 `ENABLE_AI_ROUTER=true`로 바꾸고 서버 환경에 `GEMINI_API_KEY`를 설정합니다. 실제 키는 커밋하지 않습니다.

## 2. Neon

- 앱 연결은 pooled `DATABASE_URL`을 사용합니다.
- migration은 direct `DATABASE_URL_UNPOOLED`를 우선 사용합니다.

```powershell
uv run alembic current
uv run alembic upgrade head
uv run alembic check
uv run python -m backend.seed.load_verified --washwise-demo
```

2026-11-11 실제 Neon에서 `0005_catalog_manual_matching (head)`까지 적용하고, 기존 의류·모델·사용자기기 행과 ID가 보존되는 것을 확인했습니다.

## 3. PC 브라우저와 Swagger

```powershell
uv run uvicorn backend.app.main:app --reload
```

`http://127.0.0.1:8000/docs`에서 `Try it out`을 누른 뒤 옷장 → 기기 → 계획 → 설정검증 순서로 호출할 수 있습니다.

## 4. 실제 휴대폰

```powershell
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8001
```

휴대폰과 PC를 같은 네트워크에 연결하고 모바일의 `EXPO_PUBLIC_API_URL`을 `http://<PC LAN IPv4>:8001`로 설정합니다. `127.0.0.1`은 휴대폰 자신이므로 사용할 수 없습니다.

## 5. 계획 호출 전 필수 데이터

- 의류 1~10건
- 현재 데모 소유자의 사용자 기기
- 공용 모델 또는 confirmed 수동 프로필
- 기계세탁 후보 의류의 확인된 세탁 방법·최대 온도·강도·색상·이염·단독세탁·탈수 상태

기존 단순 옷장 데이터는 정보가 부족하므로 `pending_confirmation_items` 또는 설정 검증 `unknown`이 정상입니다.

## 6. 한국 내수 세탁기 카탈로그 수집

기본 명령은 DB를 변경하지 않는 dry-run입니다. 실제 저장은 `--commit`을 명시해야 합니다.

```powershell
# 한국에너지공단 4개 공식 목록 확인
uv run python -m backend.app.catalog_ingest.kea

# 현재 DATABASE_URL에 원본 행과 중복 제거 모델 저장
uv run python -m backend.app.catalog_ingest.kea --commit

# 이미 완료된 자료원은 건너뛰고 재개
uv run python -m backend.app.catalog_ingest.kea --commit --resume

# LG·삼성 국내 공식 고객지원에서 정확 모델 설명서 매칭
uv run python -m backend.app.catalog_ingest.manuals --concurrency 5 --batch-size 100

# 큐에이드 공식 세탁기 목록에서 미연결 모델 재조회
uv run python -m backend.app.catalog_ingest.manuals --provider qaid --retry-unmatched --retry-errors

# 공식 PDF·HTML에서 짧은 사용법 근거 구조화
uv run python -m backend.app.catalog_ingest.usage --concurrency 3 --batch-size 5 --max-megabytes 30

# 검토한 LG 공유 설명서를 정확히 연결된 모델에 적용
uv run python -m backend.app.catalog_ingest.reviewed
uv run python -m backend.app.catalog_ingest.reviewed --commit
```

- 기간은 PRD의 고정 범위 `2011-11-11`~`2026-11-11`입니다.
- 진행 상태는 `.tmp/catalog-progress.json`, `.tmp/manual-progress.json`, `.tmp/usage-progress.json`에 저장됩니다.
- 설명서 조회 오류는 `manuals --retry-errors`, 다운로드·추출 실패는 `usage --retry-failed`로 재시도합니다.
- 추출 규칙을 바꾼 뒤에는 `usage --reprocess`를 사용합니다. 이 명령은 사람이 확인한 행을 보존하고 자동 생성된 `needs_review` 행만 교체합니다.
- 품질 필터 변경처럼 일부 문서만 영향받으면 `usage --reprocess-invalid`로 현재 필터에 걸리는 자동 행의 문서만 다시 처리합니다.
- CFF Type1 글꼴 PDF 처리를 위해 `fonttools`가 필수 의존성으로 설치됩니다.
- 자동 추출 결과는 모두 `needs_review`이며 사람이 검토하기 전 추천 근거로 확정하지 않습니다.

## 7. 검증 명령

```powershell
npm run build
uv run ruff check .
uv run pytest
```

로컬 migration 구조 검증:

```powershell
$env:DATABASE_URL='sqlite:///./migration-check.db'
$env:DATABASE_URL_UNPOOLED=$env:DATABASE_URL
uv run alembic upgrade head
uv run alembic check
```

모바일 제공물 검증:

```powershell
cd mobile
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm bundle:android
```

## 8. 현재 제한

- 데모 모드는 인증이 아니라 고정 `DEMO_OWNER_ID`를 사용합니다.
- 공식 LG 시드는 이름형 설정만 확인돼 숫자 비교 계획이 보류될 수 있습니다.
- Gemini 실제 사진 분석은 유효한 키와 테스트 사진이 필요합니다.
- 모바일 계획·설정검증은 아직 로컬 mock이므로 [모바일 인계 문서](mobile-p0-handoff.md)의 교체가 필요합니다.
- LG·삼성과 큐에이드 공식 목록을 조회합니다. 공식 조회 경로가 없는 제조사는 `unsupported_official_source`로 기록합니다.
- 일부 구형 한글 PDF의 비표준 문자 인코딩은 자동 추출 품질이 낮을 수 있어 표본 검토가 필요합니다.

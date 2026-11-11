# WashWise

WashWise는 의류별 세탁 제한과 사용자의 실제 세탁기 지원 조합을 비교해 최소 세탁 그룹과 설정 적합성을 계산하는 FastAPI·Expo 프로젝트입니다.

## 빠른 실행

```powershell
uv sync --extra dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --reload
```

실행 후 다음 주소를 확인합니다.

- 상태: `http://127.0.0.1:8000/health`
- DB 상태: `http://127.0.0.1:8000/health/db`
- OpenAPI: `http://127.0.0.1:8000/docs`

## 구현 범위

- 옷장 CRUD, 상품 참조, 필드별 출처·확인 상태·충돌 보존
- 공용 세탁기 모델·코스·실제 설정 조합 및 사용자 기기 복원
- 최대 10벌의 분류와 부분집합 DP 최소 세탁 그룹
- 실제 입력 설정의 `suitable`, `needs_change`, `unknown` 판정
- 건조 안내, 용량 확인 상태, 최신 입력 fingerprint
- Gemini 분석·공식 상품 DB 카탈로그 통합
- 추가형 Alembic `0001 → 0002 → 0003`, Neon PostgreSQL

현재 모바일은 옷장·기기·AI를 실제 API로 사용하지만 계획·설정검증 화면은 아직 로컬 mock입니다. 필요한 변경은 [모바일 인계 문서](docs/mobile-p0-handoff.md)에 있습니다.

## 공식 시드

```powershell
uv run python -m backend.seed.load_verified --washwise-demo
```

LG `WM4000HWA`의 `Warm`, `Cold`, `High` 같은 이름은 공식 원문 그대로 저장하며 근거 없는 섭씨·RPM으로 변환하지 않습니다.

## 검증

```powershell
npm run build
uv run ruff check .
uv run pytest
cd mobile
pnpm typecheck
pnpm test
pnpm bundle:android
```

세부 계약은 [공용 API 계약](docs/api-contract.md), 실행 방법은 [runbook](docs/runbook.md), 완료·제한 사항은 [완료 보고서](docs/completion-report.md)를 참고합니다.

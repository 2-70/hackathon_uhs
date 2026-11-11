# WashWise 백엔드 실행·검증 문서

## 핵심 개념

로컬 개발은 SQLite로 빠르게 시작하고, 배포 환경에서는 같은 SQLAlchemy 모델과 Alembic 마이그레이션을 Neon PostgreSQL에 적용합니다. 서버는 테이블을 자동 생성하지 않으므로 실행 전에 마이그레이션을 적용해야 합니다.

## 1. 준비 사항

- Python 3.11 이상
- `uv`
- 로컬 검증은 별도 DB 서버 없이 SQLite 사용 가능
- Neon 검증은 Neon 프로젝트와 서버 전용 접속 문자열 필요

```powershell
uv --version
uv sync --extra dev
Copy-Item .env.example .env
```

실제 비밀번호나 API 키가 들어간 `.env`는 Git에 추가하지 않습니다.

## 2. 로컬 SQLite 실행

`.env`의 기본값을 사용합니다.

```dotenv
APP_MODE=demo
DEMO_OWNER_ID=demo-user
DATABASE_URL=sqlite:///./washwise.db
ENABLE_AI_ROUTER=false
```

```powershell
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --reload
```

확인 주소:

- 서버 상태: `http://127.0.0.1:8000/health`
- DB 상태: `http://127.0.0.1:8000/health/db`
- OpenAPI: `http://127.0.0.1:8000/docs`

## 3. Neon PostgreSQL 연결

Neon 콘솔에서 받은 접속 문자열을 서버의 `DATABASE_URL`에만 설정합니다.

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

```powershell
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

- 모바일 앱에는 API 서버 주소만 전달합니다.
- Neon 접속 문자열은 모바일 코드, API 응답, 로그, 커밋에 넣지 않습니다.
- 현재 작업에서는 실제 Neon 자격 정보가 제공되지 않아 연결 검증을 수행하지 않았습니다.

## 4. 예시 시드 로더

아래 파일은 로더 형식 확인용이며 공식 검증 데이터가 아닙니다.

```powershell
uv run python -m backend.seed.load_verified --file backend/seed/examples/demo_verified_seed.example.json
```

공식 검증 파일이 준비되면 유상진 님 소유 경로인 `backend/seed/verified/`의 파일을 같은 명령으로 전달합니다. 로더는 전체 입력을 먼저 검증하고 한 트랜잭션으로 저장합니다.

## 5. API 빠른 확인

```powershell
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/health'
```

```powershell
$body = @{
    item_name = '흰 셔츠'
    category = 'shirt'
    care_temperature_celsius = 30
    source_type = 'user_input'
    verification_status = 'unconfirmed'
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri 'http://127.0.0.1:8000/api/wardrobe' `
    -ContentType 'application/json' `
    -Body $body
```

```powershell
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/wardrobe'
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/machines'
Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/user-machines'
```

전체 요청·응답 계약은 `docs/api-contract.md`에 있습니다.

## 6. 검증 명령

```powershell
uv run ruff check .
uv run pytest
```

현재 작업 환경은 Windows 샌드박스가 Python 이벤트 루프의 로컬 socketpair 생성을 제한해 HTTP 통합 테스트가 멈췄습니다. 이벤트 루프가 필요 없는 다음 검증은 통과했습니다.

```powershell
uv run pytest backend/tests/test_seed_loader.py backend/tests/test_routes_unit.py -vv
```

일반 로컬 환경에서는 전체 `uv run pytest`를 실행해 `backend/tests/test_api.py`까지 확인해야 합니다.

## 7. AI 라우터 연결

유상진 님이 `backend.app.ai.router` 모듈과 `router` 객체를 제공한 뒤 다음 값을 바꿉니다.

```dotenv
ENABLE_AI_ROUTER=true
```

AI 라우터의 개별 경로는 `/api`를 제외한 `/analyze`, `/products/match` 형태로 정의합니다. 공용 앱이 `/api` 접두사를 붙입니다.

## 8. 데모 모드 주의사항

- 모든 옷장·사용자 기기 요청은 서버 설정의 `DEMO_OWNER_ID` 한 명에게 귀속됩니다.
- 클라이언트가 보낸 사용자 ID를 신뢰하는 인증 구현이 아닙니다.
- `APP_MODE=production`으로 바꾸면 현재 사용자 API는 `AUTH_NOT_CONFIGURED` 503을 반환합니다.
- 공개 배포 전 실제 로그인·토큰 검증·사용자별 권한 확인을 별도 구현해야 합니다.

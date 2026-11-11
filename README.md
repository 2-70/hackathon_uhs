# WashWise

WashWise는 의류 사진 및 세탁 라벨 분석, 공식 상품 관리 정보 조회, 옷장 관리, 세탁기 코스 조회를 제공합니다. FastAPI와 Expo를 사용하며 DB는 로컬 SQLite 또는 Neon PostgreSQL에 연결할 수 있습니다.

## 핵심 실행

```powershell
uv sync --extra dev
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
$env:ENABLE_AI_ROUTER = 'true'
$env:GEMINI_API_KEY = Read-Host 'Gemini API key' -MaskInput
uv run alembic upgrade head
uv run python -m backend.seed.load_verified --washwise-demo
uv run uvicorn backend.app.main:app --port 8001
```

실행 후 [OpenAPI 문서](http://127.0.0.1:8001/docs)를 열거나 [모바일 앱 실행 방법](mobile/README.md)에 따라 브라우저에서 앱을 실행합니다.

## 구현 범위

- 의류·라벨 사진 분석, 검증된 상품 매칭과 공식 관리 정보 조회
- 옷장 저장·수정·삭제, 세탁기와 공식 코스 조회, 사용자 기기 등록
- 재실행 가능한 검증 시드로 공식 상품 3개와 LG WM4000HWA 코스 3개 제공
- 공용 서버의 세탁 계획과 설정 적합성 판정은 계약 단계입니다.

자세한 요청·응답 형식은 [docs/api-contract.md](docs/api-contract.md)를 참고합니다.

## Neon 연결과 실행

현재 연결 대상은 `fancy-bar-96022343` 프로젝트의 `production` 브랜치입니다.
`neon deploy`가 `.env`에 `DATABASE_URL`과 `DATABASE_URL_UNPOOLED`를 기록합니다.
FastAPI는 pooled URL, Alembic은 unpooled URL을 사용하며 표준 PostgreSQL URL을 psycopg 3 형식으로 자동 처리합니다.
`.env.local`이 있으면 `.env`보다 우선하고, 프로세스 환경변수는 두 파일보다 우선합니다.
실제 연결값이 있는 `.env`를 `.env.example`로 덮어쓰지 마세요.

```powershell
neon deploy
npm run build
uv run alembic upgrade head
uv run python -m backend.seed.load_verified --washwise-demo
```

`DATABASE_URL`이 설정되면 위의 백엔드 실행 명령으로 Neon에 연결합니다.

`npm run build`는 Python 문법, 앱 의존성 및 OpenAPI 생성을 검사합니다. 프런트엔드 번들을 만드는 명령은 아닙니다.
Node 의존성은 Neon 설정용이며 실제 API는 계속 Python FastAPI로 실행합니다.
기존 서버가 실행 중이면 종료 후 다시 시작해 새 DB 설정을 읽으세요.
로컬 `washwise.db`의 기존 데이터는 보존되며 Neon으로 자동 복사되지 않습니다.
검증 상세와 제한은 [Neon 연결 보고서](docs/neon-setup-report.md)에 기록했습니다.

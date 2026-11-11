# WashWise Backend

WashWise의 첫 번째 백엔드 기반입니다. FastAPI, SQLAlchemy, Alembic을 사용하며 로컬에서는 SQLite로 빠르게 검증하고 운영에서는 Neon PostgreSQL을 사용하도록 구성했습니다.

## 핵심 실행

```powershell
uv sync --extra dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --reload
```

실행 후 `http://127.0.0.1:8000/docs`에서 OpenAPI 문서를 확인할 수 있습니다.

## 구현 범위

- 구현: 상태 확인, 옷장 CRUD, 기기 모델·코스·지원 설정 조합 조회, 사용자 기기 등록·조회, 공식 데이터 저장 모델, 멱등성 시드 로더, 공통 오류 형식
- 계약만 제공: AI 분석, 제품 검색, 세탁 계획, 설정 적합성 판정
- 검증 완료: Neon PostgreSQL 연결, TLS, 마이그레이션, 실제 HTTP 저장·조회·수정·삭제와 시드 중복 방지
- 미검증: 유상진 님의 공식 검증 시드, 이진영 님의 실제 모바일 빌드 연동

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
npm start
```

`npm run build`는 Python 문법, 앱 의존성 및 OpenAPI 생성을 검사합니다. 프런트엔드 번들을 만드는 명령은 아닙니다.
Node 의존성은 Neon 설정용이며 실제 API는 계속 Python FastAPI로 실행합니다.
기존 서버가 실행 중이면 종료 후 다시 시작해 새 DB 설정을 읽으세요.
로컬 `washwise.db`의 기존 데이터는 보존되며 Neon으로 자동 복사되지 않습니다.
검증 상세와 제한은 [Neon 연결 보고서](docs/neon-setup-report.md)에 기록했습니다.

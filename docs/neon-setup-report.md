# Neon 연결 및 검증 보고서

- 날짜: 2026-11-11
- 대상: 조직 `org-young-queen-28724048`, 프로젝트 `fancy-bar-96022343`, 브랜치 `production`
- 서비스: Postgres만 사용합니다. 앱은 Python FastAPI이며 Neon Functions에 앱을 배포한 것은 아닙니다.

## 변경 내용

- `npm i -g neon@latest`로 CLI를 설치했습니다.
- 요청하신 `neon init -y --org-id org-young-queen-28724048 --project-id fancy-bar-96022343 --branch production --services postgres`를 실행했습니다.
- 초기화 시 Neon 플러그인, 에이전트 스킬 및 MCP 설정이 사용자 영역에 설치됐습니다.
- 브라우저 인증 후 `neon deploy`가 `.env`에 서비스 환경변수를 가져왔습니다. 실제 비밀번호는 문서에 기록하지 않습니다.
- 생성된 `neon.ts`와 npm 잠금 파일을 유지하고 Python 검사용 `npm run build`, 서버용 `npm start`를 추가했습니다.
- 기존 SQLAlchemy와 psycopg 3를 유지했습니다. 표준 PostgreSQL URL 접두사를 자동 변환하고, 마이그레이션은 `DATABASE_URL_UNPOOLED`를 사용합니다.
- `.env`, `.env.local`, `.neon`, `node_modules`가 Git에서 제외되는 것을 확인했습니다.

## 실행 결과

CLI 배포 결과:

```text
Auth complete (profile DEFAULT)
Applying to branch production (br-soft-credit-ao5e6hm1)
No changes — branch production already matches the policy.
Utilized services: Postgres
Pulled 5 Neon variables into .env
```

빌드 및 자동 테스트 결과:

```text
> build
> uv run python -m backend.build
BUILD OK: 30 Python files; 7 API paths

python -m ruff check backend/app/core/config.py backend/build.py backend/tests/test_database_config.py migrations/env.py
All checks passed!

python -m pytest -q
........... [100%]
```

11개 테스트는 메모리 SQLite에서 API 동작을 회귀 검증하고 Neon URL 처리도 확인합니다.
실제 Neon 검증은 별도 HTTP 검사로 수행했습니다.

마이그레이션 결과:

```text
Context impl PostgresqlImpl.
Running upgrade -> 0001_initial_schema
No new upgrade operations detected.
```

FastAPI를 `127.0.0.1:8011`에 실행한 후 HTTP 요청을 보냈습니다.
고유 키로 분리한 검증 데이터만 사용했고, 테스트 후 생성한 레코드만 정리했습니다.
실제 DB 종류, Neon 호스트 여부, 드라이버 TLS 연결을 확인하고 별도 DB 세션으로 HTTP 저장 결과를 대조했습니다.

```text
PASS: Neon PostgreSQL target and TLS connection
PASS: HTTP GET /health/db -> 200, database=ok
PASS: Neon seed repeated twice -> 1 product, 1 care field, 1 model, 1 course, 2 settings
PASS: HTTP model search and course settings match Neon rows
PASS: HTTP wardrobe create/read/update/delete + independent Neon row verification
PASS: HTTP user machine model/manual registration and restore + Neon row verification
PASS: HTTP unknown model -> 404; invalid wardrobe -> 422
CLEANUP OK: removed only this run's temporary records
```

## 트러블슈팅 보고서

### 발생한 오류 및 원인 파악

1. 최초 npm 설치에서 `ENOTFOUND registry.npmjs.org`가 발생했습니다. 제한된 실행 환경에서 네트워크 이름 확인이 실패했습니다.
2. 최초 빌드에서 uv 캐시 접근 거부가 발생했습니다. Python 런타임 검사에 필요한 사용자 캐시 접근이 샌드박스에서 제한됐습니다.
3. 정적 검사 명령에 존재하지 않는 `backend/core` 경로를 넣어 `E902`가 발생했습니다. 명령의 경로 오타였습니다.
4. 초기 TLS 검사에서 `pg_stat_ssl`의 내부 DB 연결을 검사해 assertion이 실패했습니다. pooled 연결에서는 앱과 pooler 사이의 TLS를 이 통계로 판정할 수 없습니다.
5. 초기화 도중 GitHub Copilot CLI가 없다는 경고가 나왔지만 Neon 플러그인·스킬 설치와 프로젝트 연결은 성공했습니다. 앱의 필수 의존성이 아닙니다.

### 해결 방법 제시

- 네트워크 및 캐시 접근이 가능한 권한으로 npm 설치와 빌드를 다시 실행해 성공했습니다.
- 올바른 `backend/app/core/config.py` 경로로 Ruff를 실행해 통과했습니다.
- TLS 검사는 psycopg가 유지하는 실제 클라이언트 연결 상태로 수정했습니다.

```python
# pooler 내부 연결 통계 대신 앱이 사용하는 실제 TLS 연결을 검사합니다.
assert connection.connection.driver_connection.pgconn.ssl_in_use
```

연결 코드의 핵심 수정은 다음과 같습니다.

```python
# Neon 표준 URL을 설치된 psycopg 3가 처리하도록 접두사만 바꿉니다.
return "postgresql+psycopg://" + value[len(prefix):]

# 마이그레이션은 직접 연결을 우선하고 로컬에서는 기존 URL을 사용합니다.
return self.database_url_unpooled or self.database_url
```

### 재발 방지 대책

- URL 변환·TLS 옵션 유지·직접 연결 선택·SQLite 유지 테스트를 추가했습니다.
- pooled URL과 direct URL은 별도 환경변수로 유지합니다.
- 검사 실패 시 대상 연결과 검사 방법의 문제를 구분하고 실제 비밀 URL은 출력하지 않습니다.
- PostgreSQL 마이그레이션과 HTTP 흐름을 각각 확인해 단순 연결 성공을 저장 검증으로 오인하지 않습니다.

## 제한과 다음 작업

- 로컬 SQLite 데이터는 그대로 남아 있고 Neon으로 자동 이전하지 않았습니다. 이번 검증 데이터도 정리했으므로 Neon 목록이 비어 있을 수 있습니다.
- 기존 서버는 재시작해야 새로운 `.env` 연결을 사용합니다. 예전 프로세스의 `/health/db` 성공만으로 Neon 연결을 확정하지 마세요.
- 공식 상품·세탁기 데이터, 실제 모바일 앱 연동, Gemini와 최적화 엔진은 이번 검증에 포함되지 않습니다.
- 현재 데모 단일 사용자 방식은 유지됩니다. 프로젝트의 `production` 브랜치 이름이 공개 서비스 인증 구현을 뜻하지는 않습니다.
- 이후 마이그레이션은 변경 내용이 생기면 개발 브랜치에서 검증한 뒤 적용하세요.

## 포트폴리오용 기록

- 한 줄 요약: 로컬 FastAPI 백엔드를 Neon PostgreSQL과 연결하고 실제 HTTP 저장 흐름과 DB 레코드를 함께 검증했습니다.
- 기여 범위: 환경변수 연결, 드라이버 URL 호환 처리, 앱·마이그레이션 연결 분리, 빌드 검사, 실제 DB 통합 검증을 수행했습니다. 모바일·AI 코드는 수정하지 않았습니다.
- 기술 선택 이유: 기존 SQLAlchemy·psycopg 3를 유지해 Python 구조를 보존하고, Alembic으로 동일 스키마를 재현했습니다. Neon CLI는 서비스 선언과 환경변수 동기화에 사용했습니다.
- 도전과 성장: 연결 풀의 내부 통계와 실제 클라이언트 TLS 상태를 구분하고, HTTP 응답과 별도 DB 세션을 대조해 실제 영속 저장을 증명했습니다.

참고: [설치된 Neon 스킬](https://github.com/neondatabase/agent-skills/tree/main/skills/neon), [Postgres 스킬](https://github.com/neondatabase/agent-skills/tree/main/skills/neon-postgres), [SQLAlchemy 연결](https://neon.com/docs/guides/sqlalchemy), [연결 풀링](https://neon.com/docs/connect/connection-pooling).

# 트러블슈팅 보고서: 백엔드 자동 검증

## 1. 정적 검사 매개변수 순서 오류

### 발생한 오류 및 원인 파악

- FastAPI `Depends(...)` 반복을 줄이기 위해 `DbSession` 타입 별칭을 도입한 뒤, `list_machine_models`에서 필수 매개변수 `db`를 기본값이 있는 쿼리 매개변수 뒤에 배치했습니다.
- Python은 기본값이 있는 매개변수 뒤에 기본값이 없는 매개변수를 허용하지 않아 Ruff가 문법 오류를 보고했습니다.

### 해결 방법 제시 (수정된 코드 포함)

```python
def list_machine_models(
    db: DbSession,
    query: str | None = Query(default=None, min_length=1, max_length=100),
    machine_type: str | None = Query(default=None, min_length=1, max_length=40),
) -> list[MachineModel]:
```

- 필수 의존성인 `db`를 선택 매개변수보다 앞에 배치했습니다.

### 재발 방지 대책

- 함수 인자는 `필수 일반 인자 → 필수 의존성 → 기본값이 있는 선택 인자` 순서로 작성합니다.
- 코드 수정 직후 `uv run ruff check .`를 실행해 테스트 전에 문법 오류를 확인합니다.

## 2. TestClient 요청 멈춤

### 발생한 오류 및 원인 파악

- FastAPI 0.162.4와 Starlette 1.10.0 환경에서 `fastapi.testclient.TestClient`가 구형 `httpx` 0.28.1 호환 경로를 사용했습니다.
- Starlette는 해당 경로를 deprecated로 경고하고 `httpx2` 설치를 요구했으며, 실제 첫 HTTP 요청이 완료되지 않았습니다.

### 해결 방법 제시 (수정된 코드 포함)

```toml
[project.optional-dependencies]
dev = [
    "httpx2>=2,<3",
    "pytest>=8.3,<9",
    "ruff>=0.8,<1",
]
```

- 개발 의존성을 Starlette 1.10이 우선 지원하는 `httpx2`로 변경합니다.
- `uv sync --extra dev` 후 테스트를 다시 실행합니다.

### 재발 방지 대책

- 테스트 클라이언트가 출력하는 deprecation 경고를 무시하지 않고 의존성 요구를 확인합니다.
- `uv.lock`을 함께 유지해 검증된 FastAPI·Starlette·테스트 클라이언트 조합을 재현합니다.
- 의존성 업데이트 후에는 최소 상태 조회 요청부터 확인한 뒤 전체 테스트를 실행합니다.

## 3. httpx2 버전 범위 해결 실패

### 발생한 오류 및 원인 파악

- 처음 지정한 `httpx2>=0.1,<1` 범위에 실제 배포된 호환 버전이 없어 uv가 의존성 해를 만들지 못했습니다.
- 두 번의 resolver 출력으로 1.x는 존재하지 않고 2.x가 현재 지원 범위임을 확인했습니다.

### 해결 방법 제시 (수정된 코드 포함)

```toml
"httpx2>=2,<3"
```

- 현재 주 버전 2 범위 안에서 호환 업데이트를 받을 수 있도록 수정했습니다.

### 재발 방지 대책

- 새 패키지를 추가할 때 uv의 실제 해석 결과를 기준으로 존재하는 버전 범위를 확정합니다.
- 성공적으로 생성된 `uv.lock`을 실행 문서와 함께 유지합니다.

## 4. Windows 샌드박스의 asyncio 이벤트 루프 멈춤

### 발생한 오류 및 원인 파악

- `httpx2` 전환 후에도 HTTP 요청이 멈춰 `faulthandler`로 스레드 스택을 확인했습니다.
- `TestClient`가 아니라 최소 코드인 `asyncio.run(asyncio.sleep(0))`도 Python 3.14의 `socket._fallback_socketpair()` 내부 `accept()`에서 멈췄습니다.
- 따라서 앱 코드나 DB 세션이 아니라 현재 Windows 샌드박스가 이벤트 루프의 로컬 socketpair 생성 경로를 제한하는 환경 문제입니다.

### 해결 방법 제시

- Trio 백엔드도 내부 wakeup socketpair를 사용해 같은 제한에 걸리는 것을 추가 확인했습니다.
- 해결되지 않는 우회 의존성은 남기지 않고 테스트를 기본 asyncio 설정으로 되돌렸습니다.
- 현재 세션에서는 이벤트 루프가 필요 없는 DB·시드·라우터 함수 검증을 수행하고, HTTP 통합 테스트는 일반 개발 환경의 사용자 검증 항목으로 남깁니다.
- 실제 서버 실행도 기존처럼 Uvicorn의 기본 이벤트 루프를 사용합니다.

### 재발 방지 대책

- HTTP 테스트가 멈추면 먼저 최소 asyncio 코드로 환경 문제와 앱 문제를 분리합니다.
- 장시간 대기 대신 `faulthandler.dump_traceback_later()`로 실제 대기 지점을 확인합니다.
- 해결되지 않은 샌드박스 전용 우회 의존성은 코드에 남기지 않습니다.

## 5. SQLAlchemy 모델과 Alembic 인덱스 드리프트

### 발생한 오류 및 원인 파악

- `uv run alembic check`가 `product_key`, `machine_key` 인덱스를 일반 인덱스에서 고유 인덱스로 바꾸라는 차이를 보고했습니다.
- 모델은 `unique=True, index=True`로 정의했지만 초기 migration은 고유 제약과 일반 인덱스를 각각 생성해 같은 목적의 인덱스가 중복 표현되었습니다.

### 해결 방법 제시 (수정된 코드 포함)

```python
product_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
machine_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
```

- 고유 제약이 조회용 고유 인덱스를 제공하므로 모델의 별도 `index=True`와 migration의 일반 인덱스를 제거했습니다.
- 수정된 초기 migration으로 빈 검증 DB를 다시 만든 뒤 `alembic check`를 재실행합니다.

### 재발 방지 대책

- 새 migration을 작성한 뒤 빈 DB에 적용하고 반드시 `alembic check`로 metadata와 대조합니다.
- 같은 열에 고유 제약과 일반 인덱스를 중복 생성하지 않습니다.
- 안정 키 조회 성능은 고유 제약이 만든 인덱스로 충족되는지 먼저 확인합니다.

## 6. PowerShell의 OpenAPI `$ref` 문자열 확장

### 발생한 오류 및 원인 파악

- `python -c` 검증식에서 OpenAPI 키인 `$ref`를 큰따옴표 명령 문자열 안에 작성했습니다.
- PowerShell이 Python 실행 전에 `$ref`를 셸 변수로 확장해 빈 문자열 키가 되었고 `KeyError: ''`가 발생했습니다.

### 해결 방법 제시 (수정된 코드 포함)

```python
reference = schema_node.get("$" + "ref")
```

- PowerShell 명령 안에서는 `$`를 직접 포함하지 않도록 문자열을 나누어 OpenAPI 참조 키를 확인합니다.

### 재발 방지 대책

- PowerShell에서 Python·JSON 문자열에 `$`가 있으면 셸 확장 여부를 먼저 확인합니다.
- 복잡한 검증은 테스트 파일로 옮기고, 한 줄 명령에서는 셸 특수문자를 피합니다.

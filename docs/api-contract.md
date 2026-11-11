# WashWise 공용 API 계약 초안

## 1. 핵심 개념

모바일 앱은 서버에 옷과 기기를 등록하고, 새 요청으로 목록을 다시 읽어 화면을 복원합니다.
사진 분석과 제품 조회는 `ENABLE_AI_ROUTER=true`일 때 공용 API에서 사용할 수 있습니다. 세탁 계획과 설정 적합성 판정은 계약 단계입니다.

## 2. 공통 규칙

| 항목 | 계약 |
| --- | --- |
| 로컬 기본 주소 | `http://127.0.0.1:8000` |
| 본문 형식 | 별도 표시가 없으면 `application/json` |
| 사용자 식별 | `APP_MODE=demo`에서 서버가 `DEMO_OWNER_ID`를 지정합니다. 앱이 사용자 ID를 보내지 않습니다. |
| 인증 상태 | 데모 전용이며 공개 서비스 인증이 구현된 상태가 아닙니다. `production` 모드는 현재 503을 반환합니다. |
| 알 수 없는 값 | 빈 문자열로 추측하지 않고 `null`로 보냅니다. |
| 출처 값 | `user_input`, `physical_label`, `official_product_information`, `photo_inference` |
| 확인 상태 | `confirmed`, `unconfirmed` |
| OpenAPI | 서버 실행 후 `/docs`, `/openapi.json` |

### 공통 오류

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "요청 입력을 확인해 주세요.",
    "details": {
      "fields": [
        {
          "field": "body.item_name",
          "message": "Field required"
        }
      ]
    }
  }
}
```

| 상황 | 상태 코드 | 대표 `error.code` |
| --- | --- | --- |
| 필수 입력 누락·형식 오류 | 422 | `INVALID_INPUT` |
| 옷장 항목 없음 | 404 | `WARDROBE_NOT_FOUND` |
| 공용 기기 모델 없음 | 404 | `MACHINE_NOT_FOUND` |
| 기기 종류 불일치 | 422 | `MACHINE_TYPE_MISMATCH` |
| DB 연결 불가 | 503 | `DATABASE_UNAVAILABLE` |
| 운영 인증 미구현 | 503 | `AUTH_NOT_CONFIGURED` |
| 예상하지 못한 서버 오류 | 500 | `INTERNAL_SERVER_ERROR` |

500 응답에는 DB 접속 문자열, API 키, 내부 스택트레이스를 넣지 않습니다.

## 3. 구현된 API

| 메서드·경로 | 상태 | 목적 |
| --- | --- | --- |
| `GET /health` | 구현 | 서버 프로세스 상태 확인 |
| `GET /health/db` | 구현 | DB 연결 왕복 확인 |
| `POST /api/wardrobe` | 구현 | 옷장 등록 |
| `GET /api/wardrobe` | 구현 | 현재 소유자 옷장 목록 |
| `GET /api/wardrobe/{id}` | 구현 | 현재 소유자 옷장 단건 |
| `PATCH /api/wardrobe/{id}` | 구현 | 옷장 부분 수정 |
| `DELETE /api/wardrobe/{id}` | 구현 | 옷장 삭제 |
| `GET /api/machines` | 구현 | 공용 기기 모델 검색 |
| `GET /api/machines/{id}/courses` | 구현 | 모델의 코스·실제 설정 조합 조회 |
| `POST /api/user-machines` | 구현 | 사용자 기기 등록 |
| `GET /api/user-machines` | 구현 | 사용자 기기 재조회·복원 |

### 3.1 서버 상태

`GET /health`

```json
{
  "status": "ok",
  "mode": "demo",
  "database": null
}
```

`GET /health/db`는 DB 연결 성공 시 `database`가 `"ok"`입니다. 앱의 일반 상태 확인은 `/health`, 배포 점검은 `/health/db`를 사용합니다.

### 3.2 옷장 등록

`POST /api/wardrobe` → `201 Created`

```json
{
  "item_name": "흰 셔츠",
  "category": "shirt",
  "color": "white",
  "material": "cotton",
  "care_temperature_celsius": 30,
  "care_spin_level": "low",
  "care_dry_method": "line_dry",
  "care_notes": "표백 금지",
  "source_type": "physical_label",
  "verification_status": "confirmed",
  "source_reference": "사용자가 확인한 실물 라벨"
}
```

성공 응답에는 위 필드와 함께 `id`, 서버가 지정한 `owner_id`, `created_at`, `updated_at`이 포함됩니다.

### 3.3 옷장 조회·수정·삭제

- `GET /api/wardrobe`는 항목이 없을 때 `[]`를 반환합니다.
- `GET /api/wardrobe/{id}`는 현재 소유자 항목만 반환합니다.
- `PATCH /api/wardrobe/{id}`는 보낸 필드만 바꿉니다. 빈 JSON은 422입니다.
- `DELETE /api/wardrobe/{id}` 성공 응답은 아래와 같습니다.

```json
{
  "id": "항목 UUID",
  "deleted": true
}
```

### 3.4 공용 기기 모델 검색

`GET /api/machines?query=모델명&machine_type=washer`

두 쿼리 모두 선택입니다. `query`는 제조사·모델명·`machine_key`를 검색합니다.

```json
[
  {
    "id": "기기 모델 UUID",
    "machine_key": "manufacturer/model-key",
    "machine_type": "washer",
    "manufacturer": "제조사",
    "model_name": "모델명",
    "source_url": "https://공식-출처.example/model",
    "verification_status": "confirmed",
    "verified_scope": "공식 설명서의 표준 코스 설정 확인"
  }
]
```

### 3.5 코스와 실제 설정 조합

`GET /api/machines/{machine_id}/courses`

```json
{
  "machine": {
    "id": "기기 모델 UUID",
    "machine_key": "manufacturer/model-key",
    "machine_type": "washer",
    "manufacturer": "제조사",
    "model_name": "모델명",
    "source_url": "https://공식-출처.example/model",
    "verification_status": "confirmed",
    "verified_scope": "표준 코스"
  },
  "courses": [
    {
      "id": "코스 UUID",
      "course_key": "normal",
      "name": "표준",
      "description": "일반 의류용",
      "settings": [
        {
          "id": "설정 UUID",
          "setting_key": "30|low|null|null|null",
          "temperature_celsius": 30,
          "spin_level": "low",
          "water_level": null,
          "dry_level": null,
          "duration_minutes": null,
          "source_url": "https://공식-출처.example/manual",
          "verification_status": "confirmed"
        },
        {
          "id": "설정 UUID",
          "setting_key": "40|medium|null|null|null",
          "temperature_celsius": 40,
          "spin_level": "medium",
          "water_level": null,
          "dry_level": null,
          "duration_minutes": null,
          "source_url": "https://공식-출처.example/manual",
          "verification_status": "confirmed"
        }
      ]
    }
  ]
}
```

이 응답은 `30도·약`, `40도·중` 두 조합만 확인되었다면 그 두 건만 반환합니다. `30도·중` 같은 교차 조합을 서버가 자동 생성하지 않습니다.

### 3.6 사용자 기기 등록·재조회

공용 모델 등록 예시:

```json
{
  "machine_type": "washer",
  "display_name": "우리집 세탁기",
  "machine_model_id": "기기 모델 UUID",
  "manual_input": null,
  "notes": null
}
```

수동 등록 예시:

```json
{
  "machine_type": "washer",
  "display_name": "수동 등록 세탁기",
  "machine_model_id": null,
  "manual_input": {
    "manufacturer": "알 수 없음",
    "max_temperature_celsius": 40
  },
  "notes": "제품 라벨 확인 필요"
}
```

- `machine_model_id` 또는 비어 있지 않은 `manual_input` 중 하나는 필수입니다.
- 두 값을 함께 보내면 공식 모델 참조와 등록별 추가 입력을 모두 보존합니다.
- `manual_input`은 `user_machines`에만 저장되며 공용 `machine_models`를 수정하지 않습니다.
- `POST /api/user-machines`는 201, `GET /api/user-machines`는 현재 소유자의 배열을 반환합니다.
- 응답의 `machine_model`은 공용 모델 참조가 있을 때만 객체이고 수동 등록이면 `null`입니다.

## 4. 계약만 작성된 후속 API

사진 분석과 제품 조회는 연결된 DB의 검증 카탈로그를 사용합니다.

### 4.1 의류·세탁 라벨 사진 분석

`POST /api/analyze`

요청 형식은 `multipart/form-data`입니다.

| 필드 | 형식 | 필수 | 설명 |
| --- | --- | --- | --- |
| `image` | file | 예 | JPEG, PNG 또는 WebP, 최대 40 MiB |
| `image_type` | string | 아니요 | `auto`(기본값), `garment`, `care_label` |

라벨 분석 응답의 주요 필드 예시입니다.

```json
{
  "image_type": "care_label",
  "status": "analyzed",
  "care_label": {
    "max_wash_temperature_c": {
      "value": 30,
      "source": "care_label",
      "status": "read_from_label",
      "evidence": "30"
    }
  },
  "care_guidance": ["라벨에 표시된 최대 세탁 온도는 30°C예요."],
  "care_guidance_source": "care_label",
  "photo_request": null,
  "message": "라벨에서 읽은 세탁·건조 방법이에요."
}
```

의류 사진에서 동일 상품이 확인되면 `product_lookup.product`에 상품과 출처 URL, `product_care`에 확인된 관리 정보가 포함됩니다. 추가 사진이 필요하면 `photo_request.image_type`과 `photo_request.instructions`를 화면에 표시합니다.

### 4.2 제품 매칭

`POST /api/products/match`는 품번 또는 공식 상품 URL을 입력받습니다.

```json
{
  "brand": "Nike",
  "product_code": "IX1937-001"
}
```

응답 `status`는 `matched`, `candidates`, `not_found`, `search_unavailable` 중 하나입니다. `matched`일 때 `product.id`, `product.name`, `product.source_url`로 확인된 상품을 읽습니다. 앱의 사진 분석 화면은 `POST /api/analyze`를 사용합니다.

### 4.3 제품별 관리 정보

`GET /api/products/{product_id}/care`는 매칭 응답의 `product.id`를 받습니다. `product`, `product_care`, `care_guidance`, `photo_request`를 반환합니다. `product_care`의 각 항목에는 `value`, `source`, `status`, `evidence`가 있습니다.

### 4.4 세탁 계획 생성

`POST /api/plans` — **계약만 작성, 최적화 엔진 후속 구현**

```json
{
  "request_id": "plan-123",
  "input_version": 4,
  "wardrobe_item_ids": ["옷 UUID 1", "옷 UUID 2"],
  "user_machine_id": "사용자 기기 UUID"
}
```

```json
{
  "request_id": "plan-123",
  "input_version": 4,
  "status": "ready",
  "groups": [
    {
      "group_id": "group-1",
      "wardrobe_item_ids": ["옷 UUID 1", "옷 UUID 2"],
      "recommended_course_id": "코스 UUID",
      "recommended_setting_id": "설정 UUID",
      "reasons": ["세탁 온도 조건이 같습니다."]
    }
  ],
  "warnings": []
}
```

후속 엔진은 저장된 실제 설정 조합의 `setting_id`를 선택해야 하며 존재하지 않는 교차 조합을 생성하면 안 됩니다.

### 4.5 설정 적합성 판정

`POST /api/settings/validate` — **계약만 작성, 판정 로직 후속 구현**

```json
{
  "request_id": "validate-123",
  "input_version": 1,
  "wardrobe_item_ids": ["옷 UUID"],
  "user_machine_id": "사용자 기기 UUID",
  "course_id": "코스 UUID",
  "setting_id": "실제 설정 조합 UUID"
}
```

```json
{
  "request_id": "validate-123",
  "input_version": 1,
  "status": "needs_change",
  "reasons": ["선택한 40도 설정은 의류의 확인된 최대 온도 30도보다 높습니다."],
  "suggested_setting_id": "대체 설정 UUID",
  "unknown_fields": []
}
```

`status`는 `suitable`, `needs_change`, `unknown` 중 하나입니다. 근거가 부족하면 안전하다고 추측하지 않고 `unknown_fields`와 함께 `unknown`을 반환합니다.

## 5. AI 라우터 연결 규약

- AI 담당 파일: `backend/app/ai/`, `backend/tests/ai/`, `backend/seed/verified/`
- 제공할 모듈: `backend.app.ai.router`
- 제공할 객체: 모듈 수준의 FastAPI `APIRouter`인 `router`
- AI 라우터는 `/api` 접두사와 `/analyze`, `/products/match` 등의 경로를 제공합니다.
- 공용 앱은 `ENABLE_AI_ROUTER=true`일 때 AI `router`를 `/api` 아래에 연결합니다.
- AI 모듈 내부 의존성 import가 실패하면 공용 앱이 오류를 숨기지 않습니다.
- 공용 DB 모델 import: `backend.app.db.models`
- 요청 단위 DB 의존성 import: `backend.app.api.deps.DbSession` 또는 `backend.app.db.session.get_db`
- 쓰기 트랜잭션은 데이터를 실제로 변경하는 라우터·서비스가 `commit()`합니다.
- 공용 `get_db`는 예외 시 `rollback()`하고 요청 종료 시 세션을 닫습니다.

## 6. 시드 입력 계약

실행 명령:

```powershell
uv run python -m backend.seed.load_verified --file backend/seed/verified/팀-검증-파일.json
```

필수 안정 키는 제품의 `product_key`, 기기의 `machine_key`, 모델 내부 코스의 `course_key`입니다. 설정 조합은 온도·탈수·수위·건조·시간을 순서대로 정규화한 `setting_key`로 중복을 막습니다.

로더는 전체 JSON을 먼저 검증하고 제품·기기를 하나의 트랜잭션으로 저장합니다. 같은 파일을 반복 실행하면 기존 안정 키의 값을 갱신하며 행 수가 늘지 않습니다. 현재 `backend/seed/examples/demo_verified_seed.example.json`은 형식 확인용이며 공식 검증 데이터가 아닙니다.

## 7. 모바일 복원 확인 순서

1. `POST /api/wardrobe`와 `POST /api/user-machines`의 응답 ID를 기록합니다.
2. 별도 요청으로 두 GET 목록을 호출해 ID와 저장값을 비교합니다.
3. 앱 상태를 초기화하거나 앱을 재실행합니다.
4. 화면 진입 시 GET 목록을 다시 호출하고 같은 ID가 선택 UI에 복원되는지 확인합니다.
5. 서버 프로세스를 재시작한 뒤에도 같은 DB를 사용해 목록이 유지되는지 확인합니다.

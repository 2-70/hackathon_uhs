# WashWise 공용 API 계약

## 1. 핵심 개념

서버는 옷의 관리 조건과 각 값의 출처·확인 상태를 함께 저장합니다. 세탁 계획은 확인된 조건만 실제 세탁기 모델의 지원 조합과 비교하며, 숫자 근거가 없는 `Cold`, `High`를 임의의 섭씨·RPM으로 바꾸지 않습니다.

## 2. 공통 규칙

| 항목 | 계약 |
| --- | --- |
| 로컬 주소 | `http://127.0.0.1:8000` |
| 실기기 주소 | `http://<PC의 LAN IP>:8001` |
| 사용자 | `APP_MODE=demo`에서 서버의 `DEMO_OWNER_ID` 사용 |
| 알 수 없는 값 | `null` |
| 출처 | `user_input`, `physical_label`, `official_product_information`, `photo_inference` |
| 필드 확인 상태 | `confirmed`, `unconfirmed`, `needs_confirmation`, `conflict`, `not_applicable` |
| OpenAPI | `/docs`, `/openapi.json` |

공통 오류 형식:

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "요청 입력을 확인해 주세요.",
    "details": null
  }
}
```

주요 오류 코드는 `CONFLICTING_INPUT`, `STALE_INPUT`, `WARDROBE_NOT_FOUND`, `WARDROBE_NOT_OWNED`, `USER_MACHINE_NOT_FOUND`, `MACHINE_SETTINGS_NOT_FOUND`, `SETTING_NOT_SUPPORTED`입니다.

## 3. 구현 경로

| 메서드·경로 | 목적 |
| --- | --- |
| `GET /health`, `GET /health/db` | 서버·DB 상태 |
| `POST/GET/PATCH/DELETE /api/wardrobe` | 옷장 CRUD |
| `GET /api/wardrobe/{id}/photos/{kind}` | 등록한 옷 사진 또는 세탁 라벨 조회 |
| `GET /api/machines` | 공용 모델 검색 |
| `GET /api/machines/{id}/courses` | 실제 코스·설정 조합 |
| `POST /api/machines/identify` | 세탁기 사진(`image`)에 인쇄된 모델명을 읽어 모델 찾기. `status`는 `matched`·`candidates`·`not_found`이고 `catalog_models`·`machines`에 찾은 모델을 담습니다. AI 라우터가 켜져 있을 때만 제공합니다. |
| `POST/GET /api/user-machines` | 사용자 기기 등록·복원 |
| `GET /api/catalog/models` | 한국 내수 세탁기 카탈로그 검색 |
| `GET /api/catalog/stats` | 원본·모델·설명서·사용법 적재 통계 |
| `GET /api/catalog/models/{id}/usage` | 모델별 공식 설명서와 검토 대기 사용법 |
| `POST /api/plans` | 최소 세탁 그룹 계획 |
| `POST /api/settings/validate` | 실제 입력 설정 검증 |
| `POST /api/products/match` | 검증 카탈로그 상품 매칭 |
| `GET /api/products/{id}/care` | 상품 관리 정보 |
| `POST /api/analyze` | 이미지 분석, AI 라우터 활성화 필요 |

AI 경로는 `ENABLE_AI_ROUTER=true`일 때 등록됩니다. Gemini 키가 없어도 DB 상품 조회는 가능하지만 이미지 분석은 명시적인 설정 오류를 반환합니다.

## 4. 옷장 계약

기존 scalar 요청은 그대로 사용할 수 있습니다. 새 요청은 상품 참조와 필드별 근거를 함께 보낼 수 있습니다.

```json
{
  "item_name": "흰 셔츠",
  "category": "shirt",
  "product_reference": {
    "brand": "예시 브랜드",
    "product_name": "예시 셔츠",
    "product_code": "ABC-100",
    "matched_product_id": null,
    "official_url": null
  },
  "image_reference": "private-image:123",
  "care_wash_method": "machine_wash",
  "care_temperature_celsius": 30,
  "care_wash_strength": "gentle",
  "care_max_spin_rpm": 800,
  "color_family": "light",
  "color_bleed_risk": false,
  "wash_separately": false,
  "weight_grams": 350,
  "care_tumble_dry_allowed": false,
  "source_type": "physical_label",
  "verification_status": "confirmed",
  "care_fields": [
    {
      "field_name": "care_temperature_celsius",
      "value": 30,
      "source_type": "physical_label",
      "source_reference": "label:front",
      "evidence": "30℃ 세탁 기호",
      "knowledge_status": "confirmed",
      "conflicting_values": []
    }
  ]
}
```

- 같은 요청에서 scalar와 `care_fields`의 같은 값이 다르면 422 `CONFLICTING_INPUT`입니다.
- 서로 다른 실제 출처가 충돌하면 `knowledge_status: "conflict"`와 두 개 이상의 `conflicting_values`를 저장합니다.
- `care_gentle`은 기존 모바일 하위호환 필드이며 `care_wash_strength`와 동기화됩니다.
- POST와 PATCH는 선택적으로 `photos` 객체의 `clothing`, `label` 키에 Base64로 인코딩한 JPEG, PNG, WebP를 받습니다. 사진 한 장의 업로드 한도는 12MB입니다. 서버는 JPEG로 변환해 옷 정보와 함께 저장합니다.
- PATCH는 전달한 scalar, 필드 근거, 사진 종류만 갱신합니다. 사진이 유효하지 않으면 옷 정보 변경도 반영되지 않습니다.
- 옷장 응답의 `photo_kinds`는 저장된 종류만 반환합니다. 현재 소유자의 사진은 `GET /api/wardrobe/{id}/photos/clothing` 또는 `/photos/label`에서 JPEG로 받을 수 있습니다. 옷이나 사진이 없으면 `WARDROBE_PHOTO_NOT_FOUND`를 반환합니다.

## 5. 기기 설정 계약

설정 한 행은 실제 기기에서 함께 선택 가능한 한 조합입니다.

```json
{
  "id": "설정 UUID",
  "setting_key": "안정 키",
  "temperature_celsius": null,
  "temperature_setting": "Warm",
  "wash_strength": null,
  "spin_rpm": null,
  "spin_level": "High",
  "is_default": true,
  "manual_page": 24,
  "evidence": "Cycle Guide 원문",
  "verification_status": "confirmed"
}
```

공식 LG 데이터처럼 이름만 확인된 값은 숫자가 `null`입니다. 클라이언트도 이름을 그대로 표시해야 합니다.

수동 기기를 계획에 사용하려면 `manual_input`에 `verification_status: "confirmed"`와 confirmed `settings` 배열이 필요합니다. 용량은 `capacity_verification_status: "confirmed"`인 경우에만 계산에 사용됩니다.

## 6. 한국 내수 세탁기 카탈로그

`GET /api/catalog/models`는 한 번에 최대 200건을 반환합니다. `page`, `page_size`, `query`, `machine_family`, `market_status`, `recommendation_status`, `manufacturer`를 조합해 검색합니다.

```json
{
  "items": [
    {
      "id": "모델 UUID",
      "catalog_key": "drum_washer|normalized-model",
      "machine_family": "drum_washer",
      "use_type": "household",
      "market_region": "KR",
      "model_name": "공식 목록 모델명",
      "applicant_name": "업체명",
      "manufacturer_name": "제조원",
      "capacity_kg": 21.0,
      "market_status": "candidate",
      "evidence_status": "official_list",
      "recommendation_status": "unconfirmed",
      "manual_match_status": "matched",
      "source_url": "공식 목록 URL"
    }
  ],
  "page": 1,
  "page_size": 50,
  "total": 2663,
  "total_pages": 54
}
```

- 기본 모델 정보는 한국에너지공단 공식 목록 근거이며, 설명서가 없거나 사람이 검토하지 않은 모델은 추천 확정값이 아닙니다.
- `manual_match_status`는 `matched`, `not_found`, `unsupported_official_source`, `pending`, `error_retry` 중 하나입니다.
- `GET /api/catalog/models/{id}/usage`의 `instructions`는 공식 문서에서 자동 추출한 짧은 근거입니다. `review_status: "needs_review"`인 항목은 화면에서 확정 안내가 아니라 검토 대기로 표시해야 합니다.
- 예상 세탁 시간·건조 시간은 수집하거나 추정하지 않습니다.

## 7. `POST /api/plans`

요청:

```json
{
  "request_id": "plan-20261111-001",
  "input_version": 4,
  "wardrobe_item_ids": ["옷 UUID 1", "옷 UUID 2"],
  "user_machine_id": "사용자 기기 UUID",
  "expected_item_versions": {
    "옷 UUID 1": "2026-11-11T01:00:00+00:00",
    "옷 UUID 2": "2026-11-11T01:01:00+00:00"
  }
}
```

- 의류는 1~10개이며 중복 ID를 허용하지 않습니다.
- `expected_item_versions`가 있으면 요청의 모든 의류 ID를 정확히 포함해야 합니다.
- 현재 DB의 `updated_at`과 다르면 409 `STALE_INPUT`입니다.

응답 핵심 구조:

```json
{
  "request_id": "plan-20261111-001",
  "input_version": 4,
  "input_fingerprint": "64자리 SHA-256",
  "item_versions": {"옷 UUID 1": "ISO 시각"},
  "groups": [
    {
      "group_number": 1,
      "wardrobe_item_ids": ["옷 UUID 1"],
      "setting": {
        "course_id": "코스 UUID",
        "course_key": "delicates",
        "setting_id": "설정 UUID",
        "setting_key": "안정 키",
        "temperature_celsius": 30,
        "temperature_setting": null,
        "wash_strength": "gentle",
        "spin_rpm": 800,
        "spin_level": "low"
      },
      "capacity_status": "verified",
      "total_weight_grams": 350,
      "reasons": []
    }
  ],
  "hand_wash_items": [],
  "machine_wash_prohibited_items": [],
  "pending_confirmation_items": [],
  "unsupported_items": [],
  "drying_advice": [],
  "machine_wash_count": 1,
  "capacity_status": "verified",
  "assignment_invariant": {
    "valid": true,
    "input_count": 1,
    "assigned_count": 1,
    "duplicate_item_ids": [],
    "missing_item_ids": []
  }
}
```

분류 우선순위는 기계세탁 금지 → 손세탁 → 정보 부족·출처 충돌 → 모델 설정 비교 → 최소 그룹 계산입니다. 모델의 숫자 근거가 없어 비교하지 못하면 `unsupported_items`가 아니라 `pending_confirmation_items`입니다.

## 8. `POST /api/settings/validate`

저장된 설정 ID 또는 사용자가 실제 기기에 입력한 값을 검증합니다.

```json
{
  "request_id": "setting-20261111-001",
  "input_version": 5,
  "wardrobe_item_ids": ["옷 UUID 1"],
  "user_machine_id": "사용자 기기 UUID",
  "course_id": "코스 UUID",
  "setting_id": null,
  "actual_setting": {
    "temperature_celsius": 30,
    "temperature_setting": null,
    "wash_strength": "gentle",
    "spin_rpm": 800,
    "spin_level": null
  }
}
```

응답 `status`:

- `suitable`: 모델 지원 조합이며 확인된 모든 조건 통과
- `needs_change`: 모델 미지원 또는 확인된 조건 위반
- `unknown`: 확인된 위반은 없지만 필수 비교가 남음

확인된 위반과 미확인 필드가 함께 있으면 `needs_change`가 우선합니다. `alternatives`에는 현재 모델의 실제 조합 중 모든 의류 조건을 만족하는 값만 들어갑니다. 추천 조합과 달라도 안전하면 `suitable`입니다.

## 9. 최신 응답 처리

모바일은 매 요청마다 새 `request_id`와 증가한 `input_version`을 보내고, 현재 화면 값과 둘 다 일치하는 응답만 적용합니다. 서버의 `input_fingerprint`는 의류 값·필드 근거·충돌 상태·수동 프로필·모델 설정·용량을 포함한 실제 계산 스냅샷의 해시입니다.

## 10. 시드

```powershell
uv run python -m backend.seed.load_verified --washwise-demo
uv run python -m backend.seed.load_verified --file backend/seed/examples/demo_verified_seed.example.json
```

로더는 문서 전체를 먼저 검증하고 한 트랜잭션으로 저장합니다. 안정 키가 같은 시드를 반복 적재해도 상품·코스·설정 행 수와 ID가 늘지 않습니다.

## 11. 의도적으로 만들지 않은 경로

- `/api/baskets`: 현재 모바일이 드럼 구성을 로컬 상태로 관리합니다.
- `/api/drying/recommend`: 계획과 옷장 응답의 건조 안내로 제공됩니다.
- `/api/analyze-batch`: P1 범위입니다.

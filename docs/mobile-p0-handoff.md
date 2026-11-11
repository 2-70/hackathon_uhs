# 모바일 P0 연동 인계

## 현재 확인 결과

- 옷장·기기·AI 분석은 실제 API 모듈을 사용합니다.
- `mobile/app/drum.tsx`는 선택한 옷의 저장 정보로 함께 빨기 계획을 계산합니다. 기기 정보가 있으면 확인된 코스 조합을 세탁 묶음마다 확인합니다.
- 옷 사진과 라벨 사진은 옷장 API에서 저장하고 다시 불러옵니다. 드럼에 담은 옷 ID는 기기에 보관합니다.

## 필요한 변경

1. 서버에서 최소 세탁 그룹을 계산하는 흐름은 `POST /api/plans`와 연결합니다.
2. 서버에서 기기 설정을 검증하는 흐름은 `POST /api/settings/validate`와 연결합니다.
3. 옷 추가·제거·수정 및 기기 변경마다 `input_version`을 증가시킵니다.
4. 요청마다 새 `request_id`를 만들고, 현재 두 값과 일치하는 응답만 화면에 적용합니다.
5. 응답의 `groups`, `hand_wash_items`, `machine_wash_prohibited_items`, `pending_confirmation_items`, `unsupported_items`, `drying_advice`를 각각 표시합니다.
6. `temperature_celsius`와 `spin_rpm`이 `null`이어도 `temperature_setting`, `spin_level` 이름을 그대로 표시합니다.
7. `unknown`과 `pending_confirmation_items`를 안전한 설정으로 임의 변환하지 않습니다.

전체 JSON 계약은 [api-contract.md](api-contract.md)를 기준으로 합니다.

## 실기기 실행

PC와 휴대폰을 같은 네트워크에 연결한 뒤 서버를 실행합니다.

```powershell
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8001
```

모바일 환경변수는 PC의 LAN IPv4를 사용합니다.

```dotenv
EXPO_PUBLIC_API_URL=http://192.168.x.x:8001
```

`127.0.0.1`은 휴대폰 자신을 의미하므로 실기기 주소로 사용할 수 없습니다. 먼저 휴대폰 브라우저에서 `http://<PC LAN IP>:8001/health`가 열리는지 확인하고, 열리지 않으면 Windows 방화벽의 8001 포트 허용 여부를 확인합니다.

## 완료 판정 기준

- 분석 → 옷장 저장 → 드럼 추가 → `/api/plans` → `/api/settings/validate` → 옷 수정 후 재계산 → 건조 안내가 실제 Android 기기에서 이어집니다.
- 앱 재실행 후 옷장·사용자 기기가 복원됩니다.
- 느리게 도착한 이전 `request_id` 또는 낮은 `input_version` 응답은 화면을 덮어쓰지 않습니다.

현재는 위 모바일 코드 교체와 실제 Android 전체 흐름이 미완료입니다.

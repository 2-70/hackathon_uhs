# AI 사진 분석

`POST /api/analyze`에 사진 한 장을 `multipart/form-data`로 보낸다. 파일 필드는 `image`이고 JPEG, PNG, WebP를 지원한다. 휴대폰에서 저장한 `.jpg` 파일이 MPO 형식이면 주 사진을 촬영 방향에 맞춰 JPEG로 변환한다. 최대 40 MiB, 3,200만 픽셀까지 올릴 수 있다. `image_type`은 `garment`, `care_label`, `auto` 중 하나이며 기본값은 `auto`다. 긴 변의 상한은 `care_label`에서 3,072픽셀, `garment`와 `auto`에서 2,560픽셀이다. 8 MiB 또는 긴 변의 상한을 넘는 사진은 방향을 보정하고 상한에 맞춰 JPEG로 변환한다.

- `garment`에는 의류 종류·색상·패턴·브랜드·제품명·품번 단서가 담긴다. 의류 사진은 기준 사진 또는 브랜드와 품번이 일치하는 상품을 검증 카탈로그에서 조회한다.
- 상품이 일치하면 `product_lookup.product`에 공식 페이지와 상품 정보를, `product_care`에 공식 관리 정보와 근거를 반환한다.
- `care_guidance`의 세탁·건조 조건은 실물 라벨이나 공식 상품 안내에서 확인한 값을 사용한다. 옷 전체 사진만으로 확인할 수 있는 관리 정보는 색상에 따른 분리 세탁 안내이며 `care_guidance_source`에 `estimated`로 표시한다. 실물 라벨과 공식 상품 안내는 각각 `care_label`, `official_product`로 표시한다.
- `care_label`에는 실물 라벨의 원문과 읽을 수 있는 관리 조건이 담긴다. 상품이나 관리 조건을 확인하기 어려우면 `capture_label`과 `manual_entry`를 반환한다.
- `photo_request`는 추가로 필요한 사진의 종류(`image_type`)와 촬영 안내(`instructions`)를 반환한다. 라벨의 위치와 필요한 기호를 안내하고, 흐림·빛 반사·잘림이 확인되면 촬영 방법도 알려준다. 촬영 안내는 `message`에서도 확인할 수 있다.
- 각 필드의 `value`, `source`, `status`, `evidence`로 판독 결과와 근거를 표시한다. 확인하지 못한 값은 `null`이고 상태는 `needs_confirmation`이다. `next_actions`는 다시 촬영하거나 직접 입력하는 화면으로 연결할 때 사용한다.
- Gemini 호출 오류는 `detail.code`와 한국어 `detail.message`를 반환한다. 업로드 필드 자체가 빠졌거나 사진 유형이 잘못되면 FastAPI의 입력 검증 오류를 반환한다.

예를 들어 라벨에서 `30`이 적힌 세탁통 기호를 읽으면 `care_label.max_wash_temperature_c`는 아래와 같다.

```json
{
  "value": 30,
  "source": "care_label",
  "status": "read_from_label",
  "evidence": "세탁통 기호 안의 숫자 30"
}
```

## 로컬 실행

Windows에서는 `backend/tests/ai/start-preview.cmd`를 탐색기에서 열거나 저장소 루트의 PowerShell에서 아래 명령을 실행한다.

```powershell
& '.\backend\tests\ai\start-preview.cmd'
```

기존 `GEMINI_API_KEY`가 있으면 사용하고, 새 창에서 시작할 때는 키를 한 번 입력한다. 사진 없는 짧은 생성 요청으로 Gemini가 실제 응답하는지 먼저 확인한다(소량의 API 사용량 발생). 키가 잘못되면 같은 창에서 다시 입력할 수 있다. 연결이 지연되면 Enter로 재확인하거나 `s`를 눌러 테스트 화면을 열고 사진 요청을 직접 시도할 수 있다. 서버가 준비되면 브라우저에 분석 테스트 화면을 연다. 창을 켜 둔 상태에서 사진을 계속 바꿔 테스트할 수 있고, 백엔드 앱의 Python 코드나 검증 데이터 JSON을 저장하면 서버가 같은 주소에서 자동으로 다시 시작한다. `8000`번 포트가 사용 중이면 다음 빈 포트를 사용하며 주소를 터미널에 표시한다.

Python 3.11 이상이 있는 PowerShell에서 저장소 루트 기준으로 실행한다. 키와 모델은 서버 환경변수로 읽는다. 기본 `gemini-3.6-flash`가 502, 503, 504를 반환하면 같은 사진과 판독 규칙으로 `gemini-3.5-flash`를 호출한다. `GEMINI_MODEL`에 다른 모델을 직접 지정하면 그 모델을 사용한다.

3.6 Flash는 응답 시간을 줄이기 위해 `thinkingLevel`을 `minimal`로 설정한다. [Gemini 추론 설정](https://aistudio.google.com/docs/thinking?generate-content=true#thinking-levels)

같은 파일을 같은 사진 유형으로 다시 올리면 성공한 라벨 판독이나 종류·색상을 확인한 의류 판독을 최대 5분 동안 재사용한다. 서버 메모리에 원본 대신 파일 해시와 판독 결과를 최대 64개 보관한다. 상품 조회와 세탁 안내 생성은 요청마다 수행한다.

Gemini 일시 오류(408/429/500/502/503/504)와 통신 오류는 지수 백오프와 짧은 무작위 대기 후 최대 3회까지 시도한다. 재시도 대기를 포함한 전체 Gemini 호출 제한은 100초이며 개별 통신 응답 제한은 45초다. 키·권한·모델 설정 오류는 재시도하지 않는다. 등록된 기준 사진과 정확히 일치하면 Gemini 호출 없이 공식 관리 정보를 반환한다. [Google의 재시도 지침](https://ai.google.dev/gemini-api/docs/troubleshooting)

개발용 서버의 `POST /api/check-connection`은 사진 없이 실제 모델 응답을 확인한다. `GET /api/available-models`는 현재 키로 조회 가능한 모델 목록을 보여 준다. 목록에 나타나더라도 실제 생성이 불가능할 수 있으므로 연결 확인을 사용한다. 두 진단 경로는 공용 AI 라우터에 포함되지 않는다. 연결 오류에 서버 재시작이 필요한 것은 아니며, 같은 화면에서 다시 요청할 수 있다.

```powershell
python -m pip install -r backend/tests/ai/requirements.txt
$env:GEMINI_API_KEY = Read-Host 'Gemini API key' -MaskInput
python -m uvicorn backend.app.ai.preview:app
```

브라우저에서 `http://127.0.0.1:8000/docs`의 `POST /api/analyze`를 열어 `Try it out`으로 사진을 올린다. CLI에서는 아래처럼 요청한다.

```powershell
curl.exe -F 'image=@C:/photos/label.jpg' -F 'image_type=care_label' http://127.0.0.1:8000/api/analyze
```

## 상품 카탈로그와 웹 이미지 검색

로컬 시연에서는 `backend/seed/verified/products.json`에서 공식 출처와 확인한 관리 조건을 읽는다. 사진 분석과 아래 두 API가 같은 카탈로그를 사용한다.

| 요청 | 동작 |
| --- | --- |
| `POST /api/products/match` | JSON의 `brand`와 `product_code` 또는 `source_url`로 등록된 상품을 확인한다. `garment_type`과 `color`는 후보 검색 단서로 사용한다. |
| `GET /api/products/{product_id}/care` | 상품 ID의 공식 관리 정보와 출처를 조회한다. 공식 자료에 없는 항목은 값이 없고 상태는 `needs_confirmation`이다. |

예를 들어 검색에 `{"brand":"나이키","product_code":"IX1937-001"}`을 보내면 `matched`와 `product_code` 확인 방법, 상품 ID `nike-ix1937-001`을 받는다. 공식 링크가 일치하면 확인 방법은 `official_url`이다. 상충하는 식별 정보나 브랜드·의류 종류만으로 찾은 결과는 `candidates`로 표시하며, 후보에는 공식 세탁 정보를 붙이지 않는다. 일치하거나 유사한 항목이 없으면 `not_found`, 조회 장애는 HTTP 503과 `search_unavailable`을 반환한다.

등록한 상품 사진 파일을 그대로 올리면 `reference_photo`로 확인할 수 있다. 촬영하거나 다른 포맷으로 저장한 사진은 품번이나 공식 링크를 통해 확인한다. `POST /api/analyze`에서 동일 상품을 확정하지 못하면 바로 세탁 라벨 사진을 요청한다. 라벨을 올리면 상품명과 관계없이 읽을 수 있는 세탁 조건을 안내한다. [시연 데이터와 실행 예제](../../seed/verified/README.md)

Google Cloud Vision API를 사용하는 환경에서는 서버 시작 전에 `GOOGLE_CLOUD_VISION_API_KEY`를 설정해 등록 사진과 품번으로 찾지 못한 이미지를 검색할 수 있다. 사진을 Cloud Vision에 전송해 동일 이미지와 관련 페이지를 찾는다. 검증 카탈로그의 기준 이미지와 정확히 일치하면 공식 관리 정보를 붙인다. 일치한 이미지가 없으면 `not_found`를 반환하고 세탁 라벨 사진을 요청한다. 검색 실패는 `search_unavailable`로 표시하고 사진 분석 결과를 반환한다. 키가 없으면 검증 카탈로그에서 조회한다. [Cloud Vision Web Detection](https://docs.cloud.google.com/vision/docs/detecting-web)

## 공용 서버 연결과 테스트

공용 FastAPI 앱에서 `backend.app.ai.router.router`를 등록한다. 이 라우터에 `/api` 접두사가 들어 있다. 라우터의 런타임 의존성은 FastAPI, HTTPX, Pillow, Pydantic, python-multipart다. `preview.py`는 로컬 확인용 진입점이다.

공용 서버에서 Neon 카탈로그를 연결할 때는 `backend.app.ai.catalog.get_catalog` FastAPI 의존성을 DB 조회 함수로 교체한다. 함수는 `CatalogProduct` 목록을 반환하고, 빈 카탈로그는 빈 목록, 조회 실패는 `None`으로 반환한다. 시드 파일 형식은 [검증 데이터 설명](../../seed/verified/README.md)에 기록했다.

```powershell
python -m pytest backend/tests/ai -q
```

테스트는 Gemini와 Cloud Vision HTTP 응답을 대체하고 실제 FastAPI 업로드 경로를 호출하므로 API 키가 없어도 실행된다.

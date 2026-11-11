# AI 사진 분석

`POST /api/analyze`에 사진 한 장을 `multipart/form-data`로 보낸다. 파일 필드는 `image`이고 JPEG, PNG, WebP를 지원한다. 휴대폰에서 저장한 `.jpg` 파일이 MPO 형식이면 주 사진을 촬영 방향에 맞춰 JPEG로 변환한다. 최대 40 MiB, 3,200만 픽셀까지 올릴 수 있다. `image_type`은 `garment`, `care_label`, `auto` 중 하나이며 기본값은 `auto`다. 긴 변의 상한은 `care_label`에서 3,072픽셀, `garment`와 `auto`에서 2,560픽셀이다. 8 MiB 또는 긴 변의 상한을 넘는 사진은 방향을 보정하고 상한에 맞춰 JPEG로 변환한다.

- Gemini가 `garment`에 의류 종류·색상·패턴·브랜드·제품명·품번 단서를 먼저 읽는다. 카탈로그에서 기준 사진과 품번을 확인하고, 웹 검색을 설정한 경우 판독 단서로 상품을 검색한다.
- 상품이 일치하면 세탁 안내 유무와 관계없이 `product_lookup.product`에 상품 출처를 반환한다. `product_care`에는 출처에서 확인한 관리 정보와 근거를 담고, 필요한 경우 확인된 소재에 따른 팁을 `care_guidance`에 함께 표시한다. 패딩의 물세탁과 건조 조건은 겉감이나 충전재만으로 판단할 수 없으므로 필요한 기호를 라벨에서 확인한다.
- 옷 사진은 Gemini 요청 한 번으로 처리한다. 먼저 이미지 검색으로 후보 페이지를 찾고, 서버가 그 페이지의 상품명과 상품정보 제공고시(소재·세탁방법)를 직접 읽은 뒤, 사진 판독과 상품 확인을 한 요청에 담는다. 서버가 읽지 못한 페이지만 Gemini URL Context로 연다. 요청이 한도나 장애로 실패하면 사진만 다시 판독한다. 품번 태그 재검색은 제공하지 않으며, `search_stage=retry`는 `initial`과 같게 처리한다.
- 서버는 공개 주소로 확인된 https 페이지만 리디렉션 없이 읽는다. 사설·로컬 주소는 읽지 않는다.
- 옷의 종류를 먼저 판단한다. 패딩·가죽·코트·정장처럼 집에서 세탁하기 어려운 옷은 상품 검색을 생략하고 전문 세탁 권장과 라벨 촬영 안내를 바로 반환한다.
- 라벨이나 공개된 세탁 안내를 확인하지 못한 옷에는 옷 종류에 맞춘 일반 관리 팁을 `care_guidance`에 담고 `care_guidance_source`를 `estimated`로 표시한다. 이 팁은 온도·코스·세탁 가능 여부를 단정하지 않는다.
- `search_stage`의 `initial`(기본값)과 `retry`에서 상품을 확인하지 못하면 세탁 라벨을 요청한다. 기존 `estimate` 요청에서는 웹 검색을 생략하고 필요한 라벨 촬영을 안내한다.
- `care_label`에는 라벨의 원문과 읽을 수 있는 관리 조건이 담긴다. `message`는 확인한 세탁·건조 방법을 한국어 문장으로 설명한다. 일부 기호를 확인하기 어려운 경우 읽은 내용과 추가 촬영 안내를 함께 반환한다.
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

Swagger 대신 WashWise 화면에서 확인하려면 `& '.\backend\tests\ai\start-preview.cmd' --app`을 실행한다. 이 모드는 Expo 웹 앱과 전체 FastAPI를 같은 로컬 주소에서 실행한다. `.tmp/app-preview/washwise.sqlite3`에 검증 카탈로그를 넣고 옷장과 기기 정보를 저장한다. 미리 보기에서 화면을 수정한 뒤에는 이 명령을 다시 실행해 웹 앱을 빌드한다.

기존 `GEMINI_API_KEY`가 있으면 사용하고, 새 창에서 시작할 때는 키를 한 번 입력한다. 사진 없는 짧은 생성 요청으로 Gemini가 실제 응답하는지 먼저 확인한다(소량의 API 사용량 발생). 키가 잘못되면 같은 창에서 다시 입력할 수 있다. 연결이 지연되면 Enter로 재확인하거나 `s`를 눌러 테스트 화면을 열고 사진 요청을 직접 시도할 수 있다. 서버가 준비되면 브라우저에 분석 테스트 화면을 연다. 창을 켜 둔 상태에서 사진을 계속 바꿔 테스트할 수 있고, 백엔드 앱의 Python 코드나 검증 데이터 JSON을 저장하면 서버가 같은 주소에서 자동으로 다시 시작한다. `8000`번 포트가 사용 중이면 다음 빈 포트를 사용하며 주소를 터미널에 표시한다.

예비 키는 `GEMINI_API_KEYS`에 쉼표로 구분해 넣는다. `GEMINI_API_KEY`가 있으면 우선 시도한다. 실행 스크립트는 응답하는 키를 선택하고, 분석 중 인증이나 한도 오류가 발생하면 다음 예비 키를 시도한다. PowerShell에서 키 세 개를 입력하려면 아래 명령을 실행한다.

```powershell
$env:GEMINI_API_KEYS = (1..3 | ForEach-Object { Read-Host "Gemini API key $_" -MaskInput }) -join ','
```

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

등록한 상품 사진 파일을 그대로 올리면 `reference_photo`로 확인할 수 있다. 촬영하거나 다른 포맷으로 저장한 사진은 품번 또는 검색 결과를 통해 확인한다. 라벨을 올리면 상품명과 관계없이 읽을 수 있는 세탁 조건을 안내한다. [시연 데이터와 실행 예제](../../seed/verified/README.md)

### Google Lens로 상품 후보 검색

이미지 검색에서 검증 카탈로그 상품의 단서가 나오면, 등록한 공식 상품 사진과 업로드 사진의 무늬나 봉제를 Gemini로 비교한다. 일치하면 카탈로그에 저장된 공식 세탁 정보를 반환한다. 카탈로그에서 확인하지 못한 후보는 품번이나 상품명으로 SerpApi 텍스트 검색을 호출해 제조사 페이지를 확인한다. 공식 정보 조회가 사용량 제한이나 연결 오류로 중단되면 `search_warning`과 화면의 `message`에 원인을 표시한다. [SerpApi 텍스트 검색](https://serpapi.com/search-api)

같은 상품을 확인할 수 없으면 세탁 라벨 사진을 요청하고, 옷 사진에서 읽은 특징에 따른 관리 팁이 있으면 함께 반환한다. 라벨 사진은 상품 검색 없이 분석한다.

서버 환경변수에 `SERPAPI_API_KEY`를 설정하면 기준 사진이나 품번으로 찾지 못한 의류의 동일 이미지와 시각적 유사 이미지를 Google Lens에서 검색한다. WashWise는 사진을 JPEG로 변환하고 SerpApi의 임시 이미지 ID로 검색한다. [SerpApi Google Lens 이미지 업로드](https://serpapi.com/google-lens-upload-an-image)

Gemini URL Context로 카탈로그에 등록된 공식 페이지와 SerpApi가 찾은 제조사 페이지를 읽는다. 사진에서 읽은 품번이 같거나 상품 사진의 구별되는 특징이 일치하고 출처를 실제로 읽은 경우 `matched`를 반환한다. 공식 페이지에 명시된 세탁 조건을 가져오며, 부족한 조건은 안쪽 라벨 사진을 요청한다. 일치 여부를 확인할 수 없는 결과는 `candidates`로 이름과 링크를 최대 5개 반환한다. [Gemini URL Context](https://ai.google.dev/gemini-api/docs/generate-content/url-context)

로컬에서 Lens만 확인하려면 PowerShell에서 서버를 띄우고 `/docs`의 `POST /api/analyze`에 `image_type=garment`로 사진을 올린다. 이 모드에서는 Gemini를 사용할 수 없어도 Lens가 후보를 찾으면 응답한다.

```powershell
$env:SERPAPI_API_KEY = Read-Host 'SerpApi API key' -MaskInput
uv run uvicorn backend.app.ai.preview:app
```

`GOOGLE_CLOUD_VISION_API_KEY`를 설정하면 Lens와 제조사 페이지에서 확인하지 못한 사진도 Cloud Vision으로 조회한다. 검증 카탈로그의 기준 이미지와 정확히 일치하면 공식 관리 정보를 붙인다. [Cloud Vision Web Detection](https://docs.cloud.google.com/vision/docs/detecting-web)

## 공용 서버 연결과 테스트

공용 FastAPI 앱에서 `backend.app.ai.router.router`를 등록한다. 이 라우터에 `/api` 접두사가 들어 있다. 라우터의 런타임 의존성은 FastAPI, HTTPX, Pillow, Pydantic, python-multipart다. `preview.py`는 로컬 확인용 진입점이다.

공용 서버에서 Neon 카탈로그를 연결할 때는 `backend.app.ai.catalog.get_catalog` FastAPI 의존성을 DB 조회 함수로 교체한다. 함수는 `CatalogProduct` 목록을 반환하고, 빈 카탈로그는 빈 목록, 조회 실패는 `None`으로 반환한다. 시드 파일 형식은 [검증 데이터 설명](../../seed/verified/README.md)에 기록했다.

```powershell
python -m pytest backend/tests/ai -q
```

테스트는 Gemini, Cloud Vision, SerpApi HTTP 응답을 대체하고 실제 FastAPI 업로드 경로를 호출하므로 API 키가 없어도 실행된다.

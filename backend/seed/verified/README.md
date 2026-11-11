# WashWise 시연용 검증 데이터

`products.json`은 상품 3개, `washers.json`은 세탁기 1개와 코스별 기본 설정 3개를 제공한다. 상품별 관리 조건은 공식 출처에서 확인한 범위까지만 포함했다.

| 상품 ID | 시연 단서 | 공식 자료에서 확인한 관리 조건 |
| --- | --- | --- |
| `coor-3270` | 쿠어 에센셜 후디 멜란지그레이 등록 사진 또는 공식 URL | 면 100%, 손세탁 및 드라이클리닝, 뒤집어 세탁 권장하지 않음 |
| `nike-ix1937-001` | Nike, `IX1937-001` | 면 82%·폴리에스터 18%, 기계세탁 가능 |
| `nike-if0698-365` | Nike, `IF0698-365` | 면 80%·폴리에스터 20%, 기계세탁 가능 |

상품의 `product.source_url`은 관리 조건의 공식 출처다. `care`에는 판독 항목별 값과 근거를 담고, 출처에 없는 온도나 건조 설정은 생략한다. `reference_image_url`과 `image_sha256`은 같은 파일을 식별할 때 사용한다. 등록 사진을 시연하려면 `reference_image_url`의 파일을 내려받아 편집 없이 업로드한다. CDN이 파일을 다른 포맷으로 제공하면 품번 검색을 사용한다.

세탁기 데이터는 [LG WM4000HWA 모델 지원 페이지](https://www.lg.com/us/support/product/lg-WM4000HWA.ABWEMUS)와 [공식 설명서 24~26쪽](https://media.us.lg.com/m/6d5d734b0871fbdf/original/WM4000_Owners-Manual.pdf#page=24)에서 확인했다. 코스별 `verified_settings`는 문서에 있는 기본 물온도·탈수 조합이다. 설명서의 `Warm`, `Cold`, `Hot`과 탈수 단계는 원문 이름으로 기록했고, 조합별 섭씨 온도나 RPM이 명시되지 않아 해당 수치는 `null`이다. 수치 제한 검증에 이 값을 가정해서 사용하면 안 된다.

## 로컬 시연

실행 중인 서버의 포트에 맞춰 주소를 바꾼다. 상품 검색과 관리 정보 조회는 Gemini 키 없이 확인할 수 있다.

```powershell
$washwiseUrl = 'http://127.0.0.1:8000'
$clues = @{ brand = 'Nike'; product_code = 'IX1937-001' } | ConvertTo-Json
$match = Invoke-RestMethod -Method Post -Uri "$washwiseUrl/api/products/match" -ContentType 'application/json' -Body $clues
$match
Invoke-RestMethod "$washwiseUrl/api/products/$($match.product.id)/care" | ConvertTo-Json -Depth 8
```

| 시연 상황 | 입력 | 확인할 결과 |
| --- | --- | --- |
| 동일 상품 | `brand: Nike`, `product_code: IX1937-001` | `matched` 및 공식 출처 |
| 공식 링크 | `source_url`에 상품의 공식 URL | `matched`, `match_method: official_url` |
| 유사 후보 | `brand: Nike`, `garment_type: 맨투맨` | `candidates`, 후보 2개, 동일 상품 미확정 |
| 미등록 상품 | `brand: 미등록 브랜드`, `garment_type: 맨투맨` | `not_found` |
| 관리 조건 부족 | `GET /api/products/nike-ix1937-001/care` | 기계세탁 가능, 온도·건조는 확인 필요 |
| 조회 장애 | 자동 테스트에서 카탈로그 읽기 실패 재현 | HTTP 503, `search_unavailable` |

공용 Neon 시드 로더는 상품의 `product.id`, 세탁기의 `id`, 코스의 세탁기 ID와 `id` 조합을 사용해 중복 삽입을 피할 수 있다. 운영용 DB 테이블과 시드 실행은 공용 백엔드에서 연결한다.

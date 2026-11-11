# 이우진 담당 P0 전체 체크리스트

상태: `[x] 완료`, `[~] 외부 담당 반영·실기기·외부 키 필요`

## 기획·통합

- [x] 승인된 PRD의 충돌 처리·분류 순서·판정 우선순위·fingerprint 규칙 반영
- [x] AI 소유 파일을 변경 없이 원격 제공물에서 통합
- [x] 모바일 제공물을 변경 없이 통합
- [x] AI 라우터 `/api` 중복 방지와 Neon 카탈로그 의존성 연결
- [x] AI 런타임 의존성·공통 오류 형식·회귀 테스트
- [~] AI 분석의 `request_id`·`input_version` echo는 담당 인터페이스 보완 필요

## 데이터·migration

- [x] 의류 세탁·분리·건조·제품·사진·무게 필드
- [x] 필드별 출처·확인 상태·충돌 보존 구조
- [x] 기기 용량·이름/숫자 설정·강도·근거 필드
- [x] `0002_analysis_integration` 통합
- [x] `0003_backend_p0_planning` 추가형 migration
- [x] 기존 SQLite·Neon 행과 ID 보존
- [x] 옷장 기존 요청 하위호환과 새 계약

## 계획 엔진

- [x] 기계세탁 금지 → 손세탁 → 정보 부족/충돌 → 설정 비교 순서
- [x] 이름 설정을 숫자로 추정하지 않는 비교 불가 처리
- [x] 색상·이염·단독세탁·용량 규칙
- [x] 최대 10벌 부분집합 DP와 결정론적 동점 처리
- [x] 최소 그룹 수와 탐욕법 반례 테스트
- [x] 각 의류 중복·누락 방지 invariant
- [x] `POST /api/plans`
- [x] 그룹 근거·출처·건조 안내·fingerprint

## 설정 검증

- [x] 저장 설정 ID와 실제 입력값 요청
- [x] 모델 지원 조합·온도·강도·탈수 제한 검사
- [x] `suitable`, `needs_change`, `unknown` 우선순위
- [x] 추천과 다른 안전한 실제 조합 허용
- [x] 가능한 실제 대체 설정만 반환
- [x] `POST /api/settings/validate`

## 최신 입력·시드

- [x] `request_id`, `input_version` echo
- [x] item version과 실제 계산값 SHA-256 fingerprint
- [x] 예상 버전 불일치 409 `STALE_INPUT`
- [x] 구형 예시·공식 시드 하위호환
- [x] 공식 시드 반복 적재·원자성·안정 키
- [x] 공식 상품 3개와 LG 설명서 출처·확인 범위 재검토

## 자동·실환경 검증

- [x] 정상·오류·정보 부족·출처 충돌
- [x] 모델 미지원·이름형 비교 불가·11벌·중복·누락·타인 소유
- [x] DP 최적성·결정론·배정 invariant
- [x] `npm run build`, Ruff, 전체 pytest
- [x] SQLite migration·check·downgrade·기존 행 보존
- [x] Neon 0003 migration·check·기존 ID 보존
- [x] Neon 계획·설정검증·오류 HTTP 응답
- [x] 모바일 타입 검사·단위 테스트·Android 번들

## 모바일·외부 확인

- [x] 계획·설정검증 계약과 LAN 실행 방법 인계 문서
- [~] 모바일 로컬 mock을 실제 계획·검증 API로 교체
- [~] Android 분석→저장→드럼→계획→검증→재계산→건조 실제 흐름
- [~] 앱 재실행 복원과 오래된 응답 폐기
- [~] 유효한 Gemini 키와 실제 사진으로 외부 분석 성공 흐름

## 완료 문서

- [x] 공용 API 계약
- [x] README·runbook·환경변수
- [x] 모바일 인계
- [x] 트러블슈팅 보고서
- [x] 완료 결과·제한·포트폴리오 정리

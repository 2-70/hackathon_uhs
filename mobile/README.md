# WashWise Android

React Native와 Expo로 의류 등록부터 세탁·건조 계획 확인까지 구현하는 앱입니다. 현재는 개발용 응답을 사용합니다. 사진을 선택하거나 촬영할 수 있고, 분석 버튼을 누르면 사진 내용과 관계없이 개발용 결과가 표시됩니다. 옷장과 선택한 세탁기는 기기에 저장됩니다.

## 실행

저장소 루트에서 `mobile/`로 이동해 아래 명령을 실행합니다. Node.js 22.18 이상인 22.x 또는 Node.js 24.3 이상인 24.x와 pnpm 11.25.0을 사용합니다. 앱은 Expo SDK 58을 사용합니다.

```powershell
cd mobile
pnpm install --frozen-lockfile
pnpm start
```

Android 기기에서 SDK 58을 지원하는 Expo Go를 열고 Metro에 표시된 QR 코드를 스캔합니다. 휴대전화와 개발 PC는 같은 네트워크에 연결합니다. Android 에뮬레이터에서는 `pnpm android`를 실행합니다. [Expo 프로젝트 실행 가이드](https://docs.expo.dev/get-started/start-developing/)

## 개발용 흐름 확인

1. 홈에서 **의류 등록**을 열어 카메라로 의류를 촬영하거나 사진 보관함에서 고릅니다. 카메라 권한을 거부한 경우 사진 선택 또는 직접 입력으로 진행합니다. 사진 분석에 표시되는 관리정보를 검토하고 옷장에 저장합니다.
2. **우리 집 세탁기**에서 `WW-DEMO 100`을 검색해 등록합니다.
3. **내 옷장**에서 흰 면 티셔츠, 크림색 셔츠, 검은 데님 팬츠와 베이지 울 니트를 골라 드럼에 담습니다. **가상 드럼**에서 **세탁 분석 시작**을 누릅니다.
4. 밝은 옷과 어두운 옷이 분리되는지, 울 니트에 손세탁 안내가 표시되는지 확인합니다. 드럼에서 데님 팬츠를 빼고 계획이 다시 계산되는지 확인합니다.
5. 사용하려는 코스, 온도, 탈수를 입력해 권장 설정과 비교합니다. 앱을 다시 열어 저장한 의류와 세탁기가 남아 있는지 확인합니다.

## 검사

`mobile/`에서 실행합니다. `node --test`는 의존성을 설치하기 전에도 개발용 응답과 세탁 계획을 검사할 수 있습니다.

```powershell
node --test
pnpm typecheck
pnpm bundle:android
```

## Android APK

Android Studio, JDK 17, Android SDK Platform 37을 준비한 PC에서 아래 명령으로 Android 앱을 빌드합니다. `--device`로 연결된 기기나 에뮬레이터를 선택합니다.

```powershell
pnpm android:native --device
pnpm android:native --variant release --device
```

로컬 릴리스 APK는 `android/app/build/outputs/apk/release/app-release.apk`에서 확인할 수 있습니다. [로컬 Android 빌드 가이드](https://docs.expo.dev/guides/local-app-development/)

EAS에서 빌드할 때는 팀 Expo 계정으로 로그인하고 `mobile/`에서 프로젝트를 연결한 뒤 내부 배포용 `preview` 프로필을 사용합니다.

```powershell
pnpm dlx eas-cli@latest login
pnpm dlx eas-cli@latest init
pnpm dlx eas-cli@latest build --platform android --profile preview
```

빌드 상세 페이지에서 APK를 내려받아 기기에서 열거나 `adb install <APK 경로>`로 설치합니다. [Expo APK 빌드 가이드](https://docs.expo.dev/build-reference/apk/)

실제 API 연결과 실기기 시연 검증은 공용 API 계약이 준비된 뒤 진행합니다.

## 현재 검증 결과

- 개발용 응답 테스트 4개, TypeScript 타입 검사, Android Hermes 번들 생성, Expo 설정 확인을 통과했습니다.
- 공용 API 계약과 서버가 준비되면 실제 사진 업로드, 공식 상품 정보 조회, 옷장·세탁 계획 저장을 확인합니다.
- Android SDK와 연결된 실기기가 없는 환경에서 검사했습니다. APK 빌드·설치와 카메라·권한 흐름은 실기기 검증 단계에서 확인합니다.

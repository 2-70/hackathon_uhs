# WashWise 모바일 앱

React Native와 Expo로 의류 사진과 세탁 라벨을 분석하고, 옷장에 저장하거나 세탁기 코스를 확인할 수 있습니다. 옷장 정보와 등록한 세탁기는 API를 통해 DB에 저장합니다.

## 실행

[백엔드 실행 방법](../README.md)에 따라 API를 먼저 실행합니다. 새 PowerShell에서 저장소 루트의 `mobile/`로 이동해 아래 명령을 실행합니다. Node.js 22.18 이상인 22.x 또는 Node.js 24.3 이상인 24.x와 pnpm 11.25.0을 사용합니다.

```powershell
cd mobile
pnpm install --frozen-lockfile
$env:EXPO_PUBLIC_API_URL = 'http://127.0.0.1:8001'
pnpm web
```

웹 앱은 [localhost:8081](http://localhost:8081)에서 엽니다. Android 에뮬레이터에서는 API 주소를 `http://10.0.2.2:8001`로 설정한 뒤 `pnpm android`를 실행합니다. 실기기는 PC와 같은 네트워크에서 API를 `--host 0.0.0.0`으로 실행하고 `EXPO_PUBLIC_API_URL`에 PC의 LAN IP를 사용합니다. `pnpm start` 후 SDK 58을 지원하는 Expo Go에서 QR 코드를 스캔합니다. [Expo 프로젝트 실행 가이드](https://docs.expo.dev/get-started/start-developing/)

## 시연 흐름

1. **의류 등록**에서 의류 사진을 선택합니다. 동일 상품을 확인하면 공식 출처와 확인된 세탁 방법이 표시됩니다. 확인에 필요한 정보가 부족하면 안내에 따라 안쪽 세탁 라벨을 추가합니다.
2. **세탁 라벨**에서 세탁 기호와 글자가 보이는 사진을 분석합니다. 확인된 관리 정보를 검토하고 옷장에 저장합니다.
3. **우리 집 세탁기**에서 `WM4000HWA`를 검색하고 등록합니다. 앱을 다시 열어 의류와 세탁기가 남아 있는지 확인합니다.

## 검사

`mobile/`에서 실행합니다. `node --test`는 세탁 계획 및 개발용 테스트 데이터를 검사합니다.

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

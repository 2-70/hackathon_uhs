// Neon CLI가 배포할 서비스와 브랜치 정책의 자료형을 가져옵니다.
import { defineConfig } from "@neon/config/v1";

// Postgres는 프로젝트의 기본 서비스이며 이번에는 추가 서비스가 필요하지 않습니다.
export default defineConfig({
  // 기존 FastAPI 데모를 유지하므로 Neon Auth는 활성화하지 않습니다.
  auth: false,
  // CLI가 생성한 브랜치 정책을 유지합니다.
  branch: (branch) => {
    // 요청받은 production 기본 브랜치에는 추가 설정을 덮어쓰지 않습니다.
    if (branch.isDefault) {
      // 빈 객체는 프로젝트 기본값을 유지한다는 뜻입니다.
      return {};
    }
    // 이후 새 개발 브랜치를 만들 때만 만료 기간을 적용합니다.
    if (!branch.exists) {
      // 사용하지 않는 개발 브랜치가 계속 남지 않도록 7일 후 만료합니다.
      return { ttl: "7d" };
    }
    // 이미 존재하는 다른 브랜치의 설정도 변경하지 않습니다.
    return {};
  },
});

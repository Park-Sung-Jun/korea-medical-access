// 지도 API 키 설정 예시. 이 파일을 config.js 로 복사하고 키를 채우세요.
// config.js 는 .gitignore 에 넣어 커밋하지 마세요.
// VWorld/Kakao 키는 "도메인 등록형"이라 클라이언트 노출이 정상이지만,
// 사용할 도메인(개발: http://localhost:8080)을 각 키 발급 콘솔에 등록해야 동작합니다.
window.MAP_KEYS = {
  // VWorld 인증키 (https://www.vworld.kr/dev/v4api.do). 등록 도메인에서만 동작.
  vworld: "",
  // (선택) Kakao JavaScript 키. 현재 지도는 MapLibre라 Kakao 타일은 미사용.
  kakao: "",
  // OpenRouteService 키 (클릭형 등시선용, 브라우저에서 직접 호출). 무료 발급: openrouteservice.org/dev
  ors: "",
};

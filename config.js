// 공개 배포에 포함되는 지도 키 (도메인 등록형이라 클라이언트 노출이 정상).
//  - VWorld 키: VWorld 콘솔에서 사용 도메인(localhost, vercel 도메인) 등록/제한 권장.
//  - ORS 키는 여기 두지 않는다(도메인 제한 불가) → 공개는 서버리스 /api/iso, 로컬은 config.local.js.
window.MAP_KEYS = {
  vworld: "56A8CCC0-46F4-346B-B9E6-B20C008A24D3",
  kakao: "",          // MapLibre에선 카카오 타일 미사용(좌표계/SDK 비호환)
  ors: ""             // 공개: 서버리스 프록시 / 로컬: config.local.js 에서 채움
};

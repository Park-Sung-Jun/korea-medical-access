# 배포 가이드 (Netlify / Vercel)

정적 배포 번들은 `dist/` (또는 `dist.zip`, 843KB)에 있습니다.
랜딩 = 리포트(`index.html`), 지도 = `map.html`. 데이터는 `dist/data/`.

## 방법 A — Netlify Drop (가장 쉬움, CLI/계정 가입만)
1. https://app.netlify.com/drop 접속 (로그인)
2. **`dist` 폴더를 통째로 드래그&드롭** (또는 `dist.zip` 업로드)
3. 즉시 `https://<random>.netlify.app` 공개 URL 발급. Site settings에서 이름 변경 가능.

## 방법 B — Vercel
- CLI: `npm i -g vercel` → `cd dist && vercel --prod`
- 또는 vercel.com 대시보드에서 `dist` 폴더 import

## 배포 전 점검(이미 처리됨)
- `node_modules`, `pop_202512.json`(원천), CSV, scripts 제외 → 번들 2.4MB
- **ORS 키 제거됨**: 공개 노출 시 쿼터 도용 방지. 메인 3뷰·바이베리엇·리포트·OHCA 차트는 키 없이 정상.
  - "여기서 등시선"(지도 클릭) 모드만 비활성 → 공개로도 쓰려면 `dist/config.js`의 `ors`에 키를 넣고 재배포(쿼터 위험 감수).
  - VWorld 배경지도를 쓰려면 `vworld` 키 + 발급 콘솔에 배포 도메인(예: `https://<name>.netlify.app`) 등록.
- 데이터는 전부 공개 출처(보건복지부·KOSIS·HIRA·OSM)라 공개 안전.

## 재빌드
데이터/리포트 수정 후: `python scripts/build_dist.py` → `dist/` 갱신 → 다시 드롭.

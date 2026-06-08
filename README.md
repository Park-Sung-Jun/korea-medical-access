# 상급종합병원(3차병원) 접근성 · 고령화 지도

전국 제5기 상급종합병원(2024–2026, 47개소) + 강원대학교병원 = **48개** 기준 등시선(isochrone) 지도.
세 가지 뷰를 전환하며 본다. 참고: [vw-lab 지하철 등시선 지도](https://www.vw-lab.com/130).

| 뷰 | 내용 |
|---|---|
| **접근성 등시선** | 가장 가까운 상급종합병원까지 자동차 운전 시간(15/30/60/90분) |
| **접근성 × 고령화** | 시군구 바이베리엇 코로플레스 — 고령화 높고 접근성 나쁜 **의료 취약지** 강조 |
| **고령화지수** | 시군구별 고령화지수(65세↑/0–14세×100) 단일 코로플레스 |

배경지도는 우상단에서 선택(CARTO 3종 · VWorld 3종).

## 구조
```
data/
  hospitals.json            # 47개 병원 명단+좌표(보건복지부, Nominatim 검증)
  hospitals.geojson         # 병원 포인트(생성)
  pop_202512.json           # KOSIS 주민등록 2025.12 (고령화 계산 원천)
  sigungu.geojson           # 시군구 경계+고령화지수(생성)
  isochrones.geojson        # 운전 등시선 밴드(ORS 실행 후 생성)
  sigungu_bivariate.geojson # 접근성×고령화 결합(combine 실행 후 생성)
scripts/
  verify_coords.py          # Nominatim 좌표 검증/보정
  build_sigungu.py          # 행정동→시군구 dissolve + 고령화지수
  fetch_isochrones.py       # ORS 등시선 호출 → GeoJSON
  combine_bivariate.py      # 접근성×고령화 결합
  fill_access.py            # 60분 등시선 밖 사각지대 → Matrix API로 실제 운전시간 실측
  fetch_hira.py             # 심평원 병원정보(전국 의료기관) → 시군구별 종합병원 수 공간조인 병합
  enrich_health.py          # (선택) 시군구 보건지표 CSV → 건강위험 3번째 축 병합
  fetch_ohca.py             # (시도 단위) 급성심장정지 발생률·생존율 → 접근성 검증 상관분석
index.html                  # MapLibre GL 지도(3뷰 + 배경지도 선택)
config.js                   # 지도 키(VWorld 등). config.example.js 복사해 작성
```

## 사용법
1. **키 설정**
   - OpenRouteService 무료 키 발급: https://openrouteservice.org/dev/#/signup
   - (선택) VWorld 키를 `config.js`의 `vworld`에 넣고 발급 콘솔에 도메인(`http://localhost:8080`) 등록
2. **데이터 생성**
   ```powershell
   $env:ORS_API_KEY="발급받은_ORS_키"
   python scripts/fetch_isochrones.py        # 등시선 (15/30/45/60분 — ORS 무료는 60분이 상한)
   python scripts/combine_bivariate.py       # 접근성×고령화 결합
   python scripts/fill_access.py             # 60분 밖 시군구는 Matrix로 실제 분 채움
   ```
   - `build_sigungu.py`(고령화)는 이미 생성됨. 재생성하려면 동일하게 실행.
3. **지도 열기** (파일 직접 열면 fetch 차단됨 → 로컬 서버 필수)
   ```powershell
   python -m http.server 8080
   # http://localhost:8080
   ```

## 데이터 출처
- 병원 명단: 보건복지부 「제5기('24~'26) 상급종합병원 지정 기관현황」(47개소)
- 인구/고령화: 통계청 KOSIS 주민등록인구 2025.12 (park-sung-jun/pop-pyramid)
- 시군구 경계: 행정동 경계(raqoon886/Local_HangJeongDong) dissolve, 강원·전북·군위 코드 개편 반영
- 도로망/등시선: OpenRouteService(OSM, driving-car) · 좌표 검증: OSM Nominatim

## 참고
- 고령화지수 = 65세 이상 ÷ 0–14세 × 100. 100 초과면 노인이 유소년보다 많음.
- 바이베리엇 분류: 고령화 3분위 × 접근성(≤30 / 30–60 / >60분). `A3B3`=최취약.
- **ORS 무료 티어는 driving-car 등시선을 최대 3600초(60분)로 하드캡**한다(`code 3004`). 90분 밴드 불가 → 60분 밖은 `fill_access.py`(Matrix API)로 실측 분을 채운다(`access_min_exact=True`, `access_band` 60~90/90~120/>120). 도로 미연결 섬(울릉·제주·서귀포)은 `access_suspect=True`로 과대값 플래그.

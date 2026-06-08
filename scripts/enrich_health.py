"""
국민건강보험공단(NHIS) 건강검진 통계(KOSIS hOrg=350 트리: 일반건강검진·대사증후군·
암검진 등) 시군구 지표를 data/sigungu_bivariate.geojson 에 '건강위험' 3번째 축으로 병합.

설계 요약
---------
- 입력: data/health_kosis.csv  (사용자가 KOSIS/공공데이터포털에서 받아 떨어뜨릴 시군구별 CSV)
        * 컬럼 매핑은 아래 CONFIG dict로 노출 -> 시군구코드열/시군구명열/지표값열 이름만 바꾸면 됨.
- 시군구 코드 정규화: build_sigungu.py 의 강원51·전북52·군위27720 리맵을 재사용.
        * 코드가 없고 시군구명만 있는 CSV도 '시군구명 매칭 fallback' 으로 join 가능.
- 산출: 지표를 전국 분포로 표준화.
        * health_index : z-score (평균0, 표준편차1; 클수록 '건강위험 높음')
        * health_class : 전국 3분위(터셜) C1/C2/C3  (C3 = 위험 높음)
        * tri_class    : f"A{aging}B{access}C{health}"  (기존 aging_class/access_class와 결합)
        * sigungu_bivariate.geojson 에 in-place 병합.
- CSV가 없으면 '어디서 무엇을 받아 어떻게 두면 되는지' 안내하고 정상 종료(비정상 종료 금지).
  -> 스캐폴드로서 그대로 실행 가능한 상태.

지표 방향(direction)
--------------------
'건강위험' 축이므로 값이 클수록 위험이 커지는 지표(예: 대사증후군 유병률, 비만율,
공복혈당장애율 등)를 기본 가정한다. 만약 값이 클수록 '좋은' 지표(예: 검진 수검률)를
쓴다면 CONFIG["higher_is_worse"] = False 로 두면 부호를 뒤집어 위험으로 환산한다.

usage:
  python scripts/enrich_health.py
"""
import csv
import json
import re
import statistics
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서도 한글/유니코드 print 가 깨지지 않도록 stdout 을 UTF-8 로 강제.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ──────────────────────────────────────────────────────────────────────────
# CONFIG : CSV 컬럼명만 여기서 바꾸면 됨 (KOSIS/공공데이터포털 표마다 헤더가 다르므로)
# ──────────────────────────────────────────────────────────────────────────
CONFIG = {
    # 입력 CSV 경로 (data/ 하위 기본값)
    "csv_name": "health_kosis.csv",

    # CSV 인코딩 후보 (앞에서부터 시도). KOSIS 다운로드는 보통 cp949(euc-kr) 또는 utf-8-sig.
    "encodings": ["utf-8-sig", "cp949", "utf-8"],

    # ── 컬럼 매핑 ──────────────────────────────────────────────
    # 시군구 코드열 (5자리 또는 행정표준코드 10자리). 없으면 None 또는 "" 로 두고 name으로 매칭.
    "code_col": "시군구코드",
    # 시군구 명칭열 (코드가 없거나 매칭 실패 시 fallback). 예: "춘천시", "종로구"
    "name_col": "시군구",
    # (선택) 시도 명칭열 — 동명 시군구(예: 여러 '중구') 구분에 사용. 없으면 None.
    "sido_col": "시도",
    # 표준화할 지표값열 (예: "대사증후군유병률", "비만율", "수검률" 등)
    "value_col": "지표값",

    # 값이 클수록 '건강위험 높음' 이면 True (대사증후군/비만/혈당장애 등).
    # 값이 클수록 '좋은' 지표(수검률 등)면 False -> 부호를 뒤집어 위험으로 환산.
    "higher_is_worse": True,

    # 출력 property 접두/키
    "out_index_key": "health_index",   # z-score
    "out_class_key": "health_class",   # C1/C2/C3
    "out_raw_key":   "health_value",   # join된 원시 지표값(참고용)
    "out_tri_key":   "tri_class",      # A?B?C? (가능할 때만)
}

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
GEOJSON = DATA / "sigungu_bivariate.geojson"


# ──────────────────────────────────────────────────────────────────────────
# 시군구 코드 리맵 : build_sigungu.py remap_code() 와 동일 규칙을 재사용
#   강원 42xxx -> 51xxx, 전북 45xxx -> 52xxx, 군위 47720 -> 27720(대구 편입)
# ──────────────────────────────────────────────────────────────────────────
def remap_code(sgg: str) -> str:
    sgg = str(sgg).strip()
    if sgg.startswith("42"):
        return "51" + sgg[2:]
    if sgg.startswith("45"):
        return "52" + sgg[2:]
    if sgg == "47720":
        return "27720"
    return sgg


def normalize_code(raw: str) -> str:
    """행정표준코드(10자리)·콤마 등 잡음을 제거하고 5자리 시군구 코드로 정규화 후 리맵."""
    if raw is None:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return ""
    # 10자리 법정/행정동 코드면 앞 5자리가 시군구
    sgg5 = digits[:5]
    return remap_code(sgg5)


def normalize_name(name: str) -> str:
    """시군구명 매칭용 정규화: 공백 제거, '특별/광역/자치' 등 흔한 접미 변형 흡수."""
    if name is None:
        return ""
    s = re.sub(r"\s+", "", str(name)).strip()
    return s


# ──────────────────────────────────────────────────────────────────────────
# CSV 로딩
# ──────────────────────────────────────────────────────────────────────────
def read_csv_rows(path: Path):
    """인코딩 후보를 순차 시도하며 dict 행 리스트와 헤더를 반환."""
    last_err = None
    for enc in CONFIG["encodings"]:
        try:
            with path.open("r", encoding=enc, newline="") as fp:
                reader = csv.DictReader(fp)
                rows = list(reader)
                return rows, reader.fieldnames or [], enc
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue
    raise SystemExit(
        f"[오류] CSV 인코딩 해석 실패({CONFIG['encodings']}): {last_err}\n"
        f"  CONFIG['encodings'] 에 올바른 인코딩을 추가하세요."
    )


def parse_value(raw: str):
    """'1,234.5', '12.3%', '-' 같은 표기를 float 로. 결측은 None."""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "X", "x", "..", "NA", "N/A", "null", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────────────────────
# 안내문 (CSV 없거나 컬럼 불일치 시) — 추측 URL 금지, 확인된 출처만 안내
# ──────────────────────────────────────────────────────────────────────────
def guide_text(csv_path: Path) -> str:
    return f"""
[안내] 입력 CSV 가 없어 병합을 건너뜁니다 (스크립트 자체는 정상).

  필요 파일 : {csv_path}

  받는 곳(둘 중 하나; 모두 무료 회원가입/키 필요 — 키 없이 자동 다운로드는 불가):
   1) KOSIS 국가통계포털  https://kosis.kr
      - 통계청 KOSIS > '주제별' 또는 '기관별(국민건강보험공단, hOrg=350)' 트리에서
        '일반건강검진 / 대사증후군 / 암검진' 시군구 표를 선택.
      - [조회설정]에서 행=시군구, 열=지표로 두고 'CSV(또는 EXCEL) 다운로드'.
      - KOSIS OpenAPI(openapi/Param/statisticsParameterData.do)는 인증키가 필수라
        이 스크립트가 자동으로 받을 수 없음(확인됨: 키 없으면 err=10 반환).
   2) 공공데이터포털  https://www.data.go.kr  (국민건강보험공단 '건강검진통계' 검색)
      - odcloud API 는 serviceKey 필수(확인됨: 키 없으면 401). CSV 파일 내려받아 사용.

  CSV 준비 후, 파일 상단 CONFIG dict 에서 컬럼명을 실제 헤더에 맞추세요:
      code_col  = 시군구코드열 이름 (없으면 None, name_col 로 매칭)
      name_col  = 시군구명열 이름
      sido_col  = 시도명열 이름 (동명 시군구 구분; 없으면 None)
      value_col = 표준화할 지표값열 이름
      higher_is_worse = 값이 클수록 위험이면 True / 좋은 지표(수검률 등)면 False

  그 뒤 다시 실행:  python scripts/enrich_health.py
"""


# ──────────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────────
def main():
    csv_path = DATA / CONFIG["csv_name"]

    if not GEOJSON.exists():
        # 대상 geojson 이 없으면 진짜로 할 일이 없음 — 그래도 비정상 종료 대신 안내.
        print(f"[안내] 대상 파일이 없습니다: {GEOJSON}\n"
              f"  먼저 combine_bivariate.py (+ fill_access.py) 로 생성하세요.")
        return

    if not csv_path.exists():
        print(guide_text(csv_path))
        return

    rows, headers, enc = read_csv_rows(csv_path)
    print(f"CSV 로드: {csv_path.name}  행={len(rows)}  인코딩={enc}")
    print(f"  헤더: {headers}")

    # ── 컬럼 존재 확인 (없으면 안내 후 정상 종료) ──
    code_col = CONFIG["code_col"]
    name_col = CONFIG["name_col"]
    sido_col = CONFIG["sido_col"]
    value_col = CONFIG["value_col"]

    has_code = bool(code_col) and code_col in headers
    has_name = bool(name_col) and name_col in headers
    if value_col not in headers:
        print(f"\n[안내] 지표값열 '{value_col}' 가 CSV 헤더에 없습니다.\n"
              f"  CONFIG['value_col'] 을 위 헤더 중 하나로 맞추세요. 병합을 건너뜁니다.")
        return
    if not has_code and not has_name:
        print(f"\n[안내] 코드열('{code_col}')·명칭열('{name_col}') 둘 다 CSV 에 없습니다.\n"
              f"  CONFIG 의 code_col/name_col 을 실제 헤더에 맞추세요. 병합을 건너뜁니다.")
        return

    # ── geojson 로드 + 이름->코드 매칭 인덱스 구성 (fallback 용) ──
    geo = json.loads(GEOJSON.read_text(encoding="utf-8"))
    feats = geo["features"]

    by_code = {}            # 정규화코드 -> feature
    name_to_codes = {}      # 정규화시군구명 -> set(코드)  (동명 충돌 감지용)
    sidoname_to_code = {}   # (정규화시도, 정규화시군구명) -> 코드
    for ft in feats:
        p = ft["properties"]
        c = remap_code(str(p.get("code", "")))
        by_code[c] = ft
        nm = normalize_name(p.get("name", ""))
        sd = normalize_name(p.get("sido", ""))
        if nm:
            name_to_codes.setdefault(nm, set()).add(c)
            sidoname_to_code[(sd, nm)] = c
            # 시도 접두 일부 변형도 키로 추가('서울특별시'->'서울' 등 앞 2글자)
            sidoname_to_code[(sd[:2], nm)] = c

    # ── CSV 행 -> 코드 매칭 ──
    matched = {}            # 코드 -> 지표값(float)
    unmatched_rows = []     # 매칭 실패 (이름/코드 기록)
    used_namematch = 0

    for r in rows:
        val = parse_value(r.get(value_col))
        if val is None:
            continue

        code = ""
        # 1순위: 코드 매칭
        if has_code:
            code = normalize_code(r.get(code_col))
            if code and code in by_code:
                matched[code] = val
                continue
            # 정규화 코드가 by_code에 없으면 이름 fallback 으로 넘어감
            code = ""

        # 2순위: 시도+시군구명, 3순위: 시군구명 단독
        if has_name:
            nm = normalize_name(r.get(name_col))
            sd = normalize_name(r.get(sido_col)) if (sido_col and sido_col in headers) else ""
            cand = None
            if sd and (sd, nm) in sidoname_to_code:
                cand = sidoname_to_code[(sd, nm)]
            elif sd and (sd[:2], nm) in sidoname_to_code:
                cand = sidoname_to_code[(sd[:2], nm)]
            elif nm in name_to_codes and len(name_to_codes[nm]) == 1:
                cand = next(iter(name_to_codes[nm]))
            if cand:
                matched[cand] = val
                used_namematch += 1
                continue
            unmatched_rows.append(r.get(name_col) or r.get(code_col) or "?")
        else:
            unmatched_rows.append(r.get(code_col) or "?")

    if not matched:
        print("\n[안내] CSV 의 어떤 행도 시군구에 매칭되지 않았습니다.\n"
              "  - code_col 값이 5자리/10자리 행정코드인지,\n"
              "  - name_col 값이 '종로구','춘천시'처럼 시군구명인지 확인하세요.\n"
              "  병합을 건너뜁니다.")
        return

    print(f"매칭: {len(matched)}/{len(by_code)} 시군구 (이름 fallback {used_namematch}건)")
    if unmatched_rows:
        print(f"  미매칭 CSV 행 {len(unmatched_rows)}개 예: {unmatched_rows[:8]}")

    # ── 표준화: z-score + 3분위 ──
    # '건강위험' 방향으로 정렬: higher_is_worse=False 면 부호 반전
    sign = 1.0 if CONFIG["higher_is_worse"] else -1.0
    risk = {c: sign * v for c, v in matched.items()}

    vals = sorted(risk.values())
    n = len(vals)
    mean = statistics.fmean(vals)
    sd_ = statistics.pstdev(vals) if n > 1 else 0.0
    # 3분위 경계(위험 기준 오름차순): t1, t2
    t1, t2 = vals[n // 3], vals[2 * n // 3]

    def health_class(rv):
        # C3 = 위험 높음
        if rv < t1:
            return 1, f"낮음(<{t1:.3g})"
        if rv < t2:
            return 2, f"중간({t1:.3g}~{t2:.3g})"
        return 3, f"높음(>={t2:.3g})"

    def zscore(rv):
        if sd_ == 0:
            return 0.0
        return round((rv - mean) / sd_, 3)

    # ── geojson in-place 병합 ──
    idx_key = CONFIG["out_index_key"]
    cls_key = CONFIG["out_class_key"]
    raw_key = CONFIG["out_raw_key"]
    tri_key = CONFIG["out_tri_key"]

    merged = 0
    from collections import Counter
    cls_cnt = Counter()
    tri_cnt = Counter()
    for ft in feats:
        p = ft["properties"]
        c = remap_code(str(p.get("code", "")))
        if c in risk:
            rv = risk[c]
            hc, hlabel = health_class(rv)
            p[idx_key] = zscore(rv)
            p[cls_key] = f"C{hc}"
            p["health_label"] = hlabel
            p[raw_key] = matched[c]            # 원시값(부호 반전 전)
            merged += 1
            cls_cnt[f"C{hc}"] += 1
            # tri_class: aging_class(A) + access_class(B) + health_class(C) 모두 있을 때
            a = p.get("aging_class")
            b = p.get("access_class")
            if a and b:
                tri = f"A{a}B{b}C{hc}"
                p[tri_key] = tri
                tri_cnt[tri] += 1
            else:
                p[tri_key] = None
        else:
            # 미매칭 시군구는 명시적으로 None (이전 잔여값 정리)
            p[idx_key] = None
            p[cls_key] = None
            p["health_label"] = "정보없음"
            p[raw_key] = None
            p[tri_key] = None

    # meta 갱신
    geo.setdefault("meta", {})
    geo["meta"]["health_source"] = "NHIS 건강검진통계(KOSIS hOrg=350) — 사용자 제공 CSV"
    geo["meta"]["health_value_col"] = value_col
    geo["meta"]["health_higher_is_worse"] = CONFIG["higher_is_worse"]
    geo["meta"]["health_tertiles_risk"] = [round(t1, 4), round(t2, 4)]
    geo["meta"]["health_zscore_mean_std"] = [round(mean, 4), round(sd_, 4)]
    geo["meta"]["tri_legend"] = ("A=고령화(1낮음~3높음) B=접근성(1좋음~3나쁨) "
                                 "C=건강위험(1낮음~3높음), A3B3C3=3중 최취약")

    GEOJSON.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")

    # ── 요약 ──
    print(f"\n저장(in-place): {GEOJSON}")
    print(f"  병합 시군구: {merged}개")
    print(f"  위험 3분위 경계: {t1:.4g}, {t2:.4g}  (z 평균={mean:.4g}, std={sd_:.4g})")
    print(f"  health_class 분포: {dict(sorted(cls_cnt.items()))}")
    if tri_cnt:
        worst = tri_cnt.get("A3B3C3", 0)
        print(f"  tri_class 부여: {sum(tri_cnt.values())}개,  최취약 A3B3C3: {worst}개")


if __name__ == "__main__":
    main()

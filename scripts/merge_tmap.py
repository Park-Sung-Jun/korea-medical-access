"""
TMAP 전수 교차검증 결과(tmap_xcheck_full.csv)를 sigungu_bivariate.geojson 에 병합하고
교통반영 접근성으로 바이베리엇을 재분류한다.

추가 필드:
  access_min_tmap  : 교통반영(TMAP) 운전시간(분)
  access_ratio     : TMAP/ORS 비율
  access_class_tmap: 1(<=30) / 2(30~60) / 3(>60)
  bivar_class_tmap : A{고령화}B{교통반영접근}

ORS(자유흐름) 기준과 비교 통계도 출력.
"""
import csv, json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def aclass(m):
    if m is None:
        return 3
    if m <= 30:
        return 1
    if m <= 60:
        return 2
    return 3


def main():
    src = DATA / "tmap_xcheck_full.csv"
    if not src.exists():
        raise SystemExit(f"{src} 없음 — 먼저 cross_validate_tmap.py --full 실행")
    by = {}
    for r in csv.DictReader(src.open(encoding="utf-8-sig")):
        by[r["code"]] = r

    biv = json.loads((DATA / "sigungu_bivariate.geojson").read_text(encoding="utf-8"))
    changed = matched = 0
    from collections import Counter
    dist = Counter()
    for f in biv["features"]:
        p = f["properties"]
        row = by.get(str(p.get("code", "")))
        if not row:
            continue
        matched += 1
        tm = float(row["tmap_min"]) if row.get("tmap_min") else None
        p["access_min_tmap"] = tm
        p["access_min_ors_exact"] = float(row["ors_min"]) if row.get("ors_min") else None
        p["access_ratio"] = float(row["ratio"]) if row.get("ratio") else None
        ac = aclass(tm)
        p["access_class_tmap"] = ac
        gc = p.get("aging_class")
        p["bivar_class_tmap"] = (f"A{gc}B{ac}" if gc else None)
        dist[p["bivar_class_tmap"]] += 1
        if ac != p.get("access_class"):
            changed += 1

    biv.setdefault("meta", {})["tmap_fields"] = \
        "access_min_tmap=교통반영(TMAP)분, access_ratio=TMAP/ORS, bivar_class_tmap=교통반영 바이베리엇"
    (DATA / "sigungu_bivariate.geojson").write_text(json.dumps(biv, ensure_ascii=False), encoding="utf-8")

    # 통계
    F = [f["properties"] for f in biv["features"]]
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    ratios = sorted(num(p.get("access_ratio")) for p in F if num(p.get("access_ratio")))
    over60_ors = [p for p in F if num(p.get("access_min")) is not None and num(p["access_min"]) > 60]
    over60_tmap = [p for p in F if num(p.get("access_min_tmap")) is not None and num(p["access_min_tmap"]) > 60]
    a3b3_ors = sum(1 for p in F if p.get("bivar_class") == "A3B3")
    a3b3_tmap = sum(1 for p in F if p.get("bivar_class_tmap") == "A3B3")
    triple_tmap = [p for p in F if p.get("aging_class") == 3
                   and num(p.get("access_min_tmap")) is not None and num(p["access_min_tmap"]) > 60
                   and p.get("hosp_gen_cnt", 0) == 0]

    print(f"병합: {matched}/{len(F)} 시군구")
    if ratios:
        print(f"TMAP/ORS 비율  중앙값 {ratios[len(ratios)//2]:.2f}  평균 {sum(ratios)/len(ratios):.2f}")
    print(f"접근 등급(B) ORS와 달라진 시군구: {changed}개")
    print(f"60분 초과: ORS {len(over60_ors)} → TMAP {len(over60_tmap)}")
    print(f"최취약 A3B3: ORS {a3b3_ors} → TMAP {a3b3_tmap}")
    print(f"교통반영 바이베리엇 분포: {dict(sorted(dist.items()))}")
    print(f"교통반영 삼중취약(A3·60분초과·종합0): {len(triple_tmap)}")


if __name__ == "__main__":
    main()

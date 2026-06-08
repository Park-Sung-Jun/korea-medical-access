"""
isochrones.geojson(접근성) + sigungu.geojson(고령화)을 결합해
시군구별 바이베리엇(접근성 x 고령화) 속성을 가진 sigungu_bivariate.geojson 생성.

- 접근성(access_class): 시군구 대표점(면적가중 centroid)이 포함되는 최소 등시선 밴드
    B1 = <=30분(좋음), B2 = 30~60분, B3 = >60분 또는 사각지대(나쁨)
- 고령화(aging_class): 전국 시군구 고령화지수의 3분위(터셜)
    A1 = 낮음, A2 = 중간, A3 = 높음
- bivar_class: f"A{a}B{b}"  (A3B3 = 고령화 높고 접근성 나쁨 = 최취약)

ORS 등시선(fetch_isochrones.py) 실행 후에 돌린다.
"""
import json
from pathlib import Path
from shapely.geometry import shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
ISO = DATA / "isochrones.geojson"
SGG = DATA / "sigungu.geojson"
OUT = DATA / "sigungu_bivariate.geojson"


def access_class(minutes):
    if minutes is None:
        return 3, ">60분/사각지대"
    if minutes <= 30:
        return 1, "<=30분"
    if minutes <= 60:
        return 2, "30~60분"
    return 3, ">60분/사각지대"


def main():
    if not ISO.exists():
        raise SystemExit(f"{ISO} 없음. 먼저 fetch_isochrones.py 실행.")
    iso = json.loads(ISO.read_text(encoding="utf-8"))
    sgg = json.loads(SGG.read_text(encoding="utf-8"))

    # 밴드별 누적 coverage(작은 분 = 안쪽) 폴리곤
    bands = sorted({f["properties"]["minutes"] for f in iso["features"]})
    by_band = {}
    for b in bands:
        polys = [shape(f["geometry"]).buffer(0) for f in iso["features"]
                 if f["properties"]["minutes"] == b]
        by_band[b] = unary_union(polys) if polys else None
    cum, acc = {}, None
    for b in bands:
        acc = by_band[b] if acc is None else unary_union([acc, by_band[b]])
        cum[b] = acc  # cum[b] = b분 이내 도달 가능 영역

    # 고령화 3분위
    vals = sorted(f["properties"]["aging_index"] for f in sgg["features"]
                  if f["properties"]["aging_index"] is not None)
    n = len(vals)
    t1, t2 = vals[n // 3], vals[2 * n // 3]

    def aging_class(v):
        if v is None:
            return None, "정보없음"
        if v < t1:
            return 1, f"낮음(<{t1:.0f})"
        if v < t2:
            return 2, f"중간({t1:.0f}~{t2:.0f})"
        return 3, f"높음(>={t2:.0f})"

    feats = []
    for f in sgg["features"]:
        geom = shape(f["geometry"]).buffer(0)
        rep = geom.representative_point()
        # 대표점이 들어가는 최소 분 밴드 찾기
        amin = None
        for b in bands:
            if cum[b] is not None and cum[b].contains(rep):
                amin = b
                break
        ac, alabel = access_class(amin)
        agv = f["properties"]["aging_index"]
        gc, glabel = aging_class(agv)
        p = dict(f["properties"])
        p.update({
            "access_min": amin,
            "access_class": ac, "access_label": alabel,
            "aging_class": gc, "aging_label": glabel,
            "bivar_class": (f"A{gc}B{ac}" if gc else None),
        })
        feats.append({"type": "Feature", "properties": p, "geometry": f["geometry"]})

    fc = {"type": "FeatureCollection",
          "meta": {"aging_tertiles": [round(t1, 1), round(t2, 1)],
                   "bands_min": bands,
                   "bivar_legend": "A=고령화(1낮음~3높음) B=접근성(1좋음~3나쁨), A3B3=최취약"},
          "features": feats}
    OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    cnt = Counter(f["properties"]["bivar_class"] for f in feats)
    print(f"저장: {OUT}  시군구={len(feats)}")
    print(f"고령화 3분위 경계: {t1:.1f}, {t2:.1f}")
    print("바이베리엇 분포:", dict(sorted(cnt.items())))
    print("최취약(A3B3):", cnt.get("A3B3", 0), "개 시군구")


if __name__ == "__main__":
    main()

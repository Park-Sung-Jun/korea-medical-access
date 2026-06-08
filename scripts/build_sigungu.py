"""
행정동(raqoon886/Local_HangJeongDong) 경계를 sgg(시군구)로 dissolve하고,
pop_202512.json으로 시군구별 고령화지수를 계산해 data/sigungu.geojson 생성.

고령화지수 = (65세 이상 인구 / 0-14세 인구) * 100
  - 연령밴드 인덱스: 0-14 = [0,1,2] (0-4,5-9,10-14)
  -               65+   = [13..20] (65-69 ... 100+)

출력 properties: code, name, sido, aging_index, pop_total, elderly_share(%), youth_share(%)
"""
import json, urllib.request, urllib.parse
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
POP = DATA / "pop_202512.json"
OUT = DATA / "sigungu.geojson"

BASE = "https://raw.githubusercontent.com/raqoon886/Local_HangJeongDong/master/"
SIDOS = ["서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시",
         "울산광역시","세종특별자치시","경기도","강원도","충청북도","충청남도",
         "전라북도","전라남도","경상북도","경상남도","제주특별자치도"]
SIMPLIFY_TOL = 0.0008  # 약 80m


def fetch_dong(sido):
    url = BASE + "hangjeongdong_" + urllib.parse.quote(sido) + ".geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "isochrone-build/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def aging_from_pop(reg):
    m, f = reg["m"], reg["f"]
    youth = sum(m[0:3]) + sum(f[0:3])
    elderly = sum(m[13:21]) + sum(f[13:21])
    total = reg.get("total", sum(m) + sum(f))
    idx = (elderly / youth * 100.0) if youth else None
    return {
        "aging_index": round(idx, 1) if idx is not None else None,
        "pop_total": total,
        "elderly_share": round(elderly / total * 100, 1) if total else None,
        "youth_share": round(youth / total * 100, 1) if total else None,
    }


def remap_code(sgg):
    # 행정동 경계(구 코드) -> 2023~2024 개편 시도코드(특별자치도) 반영
    # 강원 42xxx -> 51xxx, 전북 45xxx -> 52xxx (시군구 하위 3자리 유지)
    if sgg.startswith("42"):
        return "51" + sgg[2:]
    if sgg.startswith("45"):
        return "52" + sgg[2:]
    if sgg == "47720":   # 군위군: 2023.7 경북 -> 대구 편입
        return "27720"
    return sgg


def main():
    pop = json.loads(POP.read_text(encoding="utf-8"))["regions"]

    # sgg -> list of polygons
    geoms = {}
    names = {}
    for sido in SIDOS:
        print(f"다운로드: {sido}")
        d = fetch_dong(sido)
        for feat in d["features"]:
            pr = feat["properties"]
            sgg = remap_code(str(pr["sgg"]))
            try:
                g = shape(feat["geometry"]).buffer(0)
            except Exception:
                continue
            geoms.setdefault(sgg, []).append(g)
            names.setdefault(sgg, (pr.get("sggnm", "").strip(), pr.get("sidonm", "").strip()))

    feats = []
    missing_pop = []
    for sgg, gl in sorted(geoms.items()):
        poly = unary_union(gl).simplify(SIMPLIFY_TOL, preserve_topology=True)
        sggnm, sidonm = names[sgg]
        props = {"code": sgg, "name": sggnm, "sido": sidonm}
        if sgg in pop:
            props.update(aging_from_pop(pop[sgg]))
        else:
            missing_pop.append((sgg, sggnm))
            props.update({"aging_index": None, "pop_total": None,
                          "elderly_share": None, "youth_share": None})
        feats.append({"type": "Feature", "properties": props, "geometry": mapping(poly)})

    fc = {"type": "FeatureCollection",
          "meta": {"source": "행정동 dissolve(raqoon886) + KOSIS 주민등록 2025-12",
                   "aging_formula": "65+/(0-14)*100", "count": len(feats)},
          "features": feats}
    OUT.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"\n저장: {OUT}  시군구={len(feats)}")
    print(f"인구데이터 미매칭 시군구: {len(missing_pop)} {missing_pop[:10]}")
    # 분포 점검
    vals = sorted(f["properties"]["aging_index"] for f in feats
                  if f["properties"]["aging_index"] is not None)
    if vals:
        n = len(vals)
        print(f"고령화지수 분포 n={n} min={vals[0]} "
              f"t33={vals[n//3]} t66={vals[2*n//3]} max={vals[-1]}")


if __name__ == "__main__":
    main()

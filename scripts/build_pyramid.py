"""
pop_202512.json(3904개 지역, 연령·성별)에서 시군구(250)만 추려
data/pop_pyramid.json 생성 — sigungu_bivariate.geojson 의 code 로 키를 맞춘다.
지도에서 시군구 클릭 시 그 지역 인구 피라미드(연령·성별)를 즉시 렌더.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"


def reverse_remap(code):
    """sigungu(신코드) -> pop가 쓸 수 있는 구코드 후보."""
    cands = [code]
    if code.startswith("51"):
        cands.append("42" + code[2:])
    if code.startswith("52"):
        cands.append("45" + code[2:])
    if code == "27720":
        cands.append("47720")
    return cands


def main():
    pop = json.loads((DATA / "pop_202512.json").read_text(encoding="utf-8"))
    bands = pop["meta"]["bands"]
    regions = pop["regions"]  # code -> {name,m,f,total}
    # 이름 인덱스(폴백)
    by_name = {}
    for code, r in regions.items():
        by_name.setdefault(r.get("name", ""), code)

    biv = json.loads((DATA / "sigungu_bivariate.geojson").read_text(encoding="utf-8"))
    out = {}
    matched = name_fb = miss = 0
    for f in biv["features"]:
        p = f["properties"]
        code = str(p.get("code", "")).strip()
        name = p.get("name", "")
        reg = None
        for c in reverse_remap(code):
            if c in regions:
                reg = regions[c]; break
        if reg is None and name in by_name:
            reg = regions[by_name[name]]; name_fb += 1
        if reg is None:
            miss += 1
            continue
        matched += 1
        out[code] = {"name": (p.get("sido", "") + " " + name).strip(),
                     "m": reg["m"], "f": reg["f"]}

    result = {"bands": bands, "regions": out}
    (DATA / "pop_pyramid.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"저장: data/pop_pyramid.json  시군구 {matched}/{len(biv['features'])} "
          f"(이름폴백 {name_fb}, 미매칭 {miss})  크기 {(DATA/'pop_pyramid.json').stat().st_size//1024} KB")


if __name__ == "__main__":
    main()

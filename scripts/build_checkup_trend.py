"""
건강검진 ⑤ 시계열·성별 — 일반건강검진 수검률 2017~2024 추이 + 성별 분리.

원천(둘 다 KOSIS long-format, 이미 다운로드됨):
  - DT_35007_N001_1.csv : 시군구별 성별 대상·수검 2018~2024 (차수 차원 없음 = 1차 기준)
  - DT_35007_N001.csv   : 〃 ~2017 (C3_NM=검진차수 → '1차검진'만 사용해 비교 가능성 유지)

산출: data/checkup_trend.json (소형, 커밋 대상)
  - national: 연도별 합계/남자/여자 수검률
  - sido    : 시도별 연도별 합계 수검률
  - sido_2024_sex: 시도별 2024 남/여 수검률·격차(여-남, %p)
  - age_2024: 연령구간별(DT_35007_N002_1) 2024 남/여/합계 수검률

usage: python scripts/build_checkup_trend.py
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
YEARS = [str(y) for y in range(2017, 2025)]
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
SEXES = {"합계": "total", "남자": "male", "여자": "female"}


def num(x):
    s = str(x or "").replace(",", "").strip()
    if s in ("", "-", "X", "x", "..", "…", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def collect():
    """acc[(year, region, sex)] = {'t': 대상, 'd': 수검}"""
    acc = {}

    def feed(path, year_ok, row_ok):
        with open(path, encoding="utf-8-sig", newline="") as fp:
            for r in csv.DictReader(fp):
                y = r.get("PRD_DE")
                if y not in YEARS or not year_ok(y) or not row_ok(r):
                    continue
                region = (r.get("C1_NM") or "").strip()
                if region != "계" and region not in SIDO:
                    continue
                sex = (r.get("C2_NM") or "").strip()
                if sex not in SEXES:
                    continue
                item = (r.get("ITM_NM") or "").strip()
                v = num(r.get("DT"))
                if v is None:
                    continue
                slot = acc.setdefault((y, region, sex), {"t": None, "d": None})
                if item == "대상인원":
                    slot["t"] = v
                elif item == "수검인원":
                    slot["d"] = v

    # 2018~2024: N001_1(차수 차원 없음). 2017: N001에서 1차검진만.
    feed(DATA / "DT_35007_N001_1.csv", lambda y: y >= "2018", lambda r: True)
    feed(DATA / "DT_35007_N001.csv", lambda y: y == "2017",
         lambda r: (r.get("C3_NM") or "").strip() == "1차검진")
    return acc


def rate(acc, y, region, sex):
    s = acc.get((y, region, sex))
    if not s or not s["t"] or s["d"] is None:
        return None
    return round(s["d"] / s["t"] * 100, 1)


AGE_BANDS = ["19세 이하", "20 ~ 24세", "25 ~ 29세", "30 ~ 34세", "35 ~ 39세",
             "40 ~ 44세", "45 ~ 49세", "50 ~ 54세", "55 ~ 59세", "60 ~ 64세",
             "65 ~ 69세", "70 ~ 74세", "75 ~ 79세", "80 ~ 84세", "85세 이상"]


def collect_age():
    """연령별(N002_1) 2024 — acc[(band, sex)] = {'t','d'}"""
    acc = {}
    with open(DATA / "DT_35007_N002_1.csv", encoding="utf-8-sig", newline="") as fp:
        for r in csv.DictReader(fp):
            if r.get("PRD_DE") != "2024":
                continue
            band = (r.get("C1_NM") or "").strip()
            sex = (r.get("C2_NM") or "").strip()
            if band not in AGE_BANDS or sex not in SEXES:
                continue
            v = num(r.get("DT"))
            if v is None:
                continue
            slot = acc.setdefault((band, sex), {"t": None, "d": None})
            item = (r.get("ITM_NM") or "").strip()
            if item == "대상인원":
                slot["t"] = v
            elif item == "수검인원":
                slot["d"] = v

    def rt(band, sex):
        s = acc.get((band, sex))
        return round(s["d"] / s["t"] * 100, 1) if s and s["t"] and s["d"] is not None else None
    short = ["≤19세" if b == "19세 이하" else "85세+" if b == "85세 이상"
             else b.replace(" ~ ", "–").replace("세", "") + "세" for b in AGE_BANDS]
    return {"bands": short,
            **{SEXES[k]: [rt(b, k) for b in AGE_BANDS] for k in SEXES}}


def main():
    acc = collect()
    out = {
        "years": [int(y) for y in YEARS],
        "national": {SEXES[k]: [rate(acc, y, "계", k) for y in YEARS] for k in SEXES},
        "sido": {s: [rate(acc, y, s, "합계") for y in YEARS] for s in SIDO},
        "sido_2024_sex": [],
        "age_2024": collect_age(),
        "source": "KOSIS DT_35007_N001(~2017 1차검진)·N001_1(2018~)·N002_1(연령별) 일반건강검진 대상·수검",
    }
    for s in SIDO:
        m, f = rate(acc, "2024", s, "남자"), rate(acc, "2024", s, "여자")
        if m is None or f is None:
            continue
        out["sido_2024_sex"].append({"sido": s, "male": m, "female": f,
                                     "gap": round(f - m, 1)})
    out["sido_2024_sex"].sort(key=lambda x: x["gap"])

    nat = out["national"]
    print("연도   합계   남자   여자  (격차 여-남)")
    for i, y in enumerate(out["years"]):
        t, m, f = nat["total"][i], nat["male"][i], nat["female"][i]
        gap = round(f - m, 1) if m is not None and f is not None else None
        print(f"{y}  {t}%  {m}%  {f}%  ({gap:+}%p)" if gap is not None else f"{y}  {t}%")
    g = out["sido_2024_sex"]
    print(f"\n2024 시도 성별격차(여-남): 최소 {g[0]['sido']} {g[0]['gap']}%p ~ 최대 {g[-1]['sido']} {g[-1]['gap']}%p")

    (DATA / "checkup_trend.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장: data/checkup_trend.json")


if __name__ == "__main__":
    main()

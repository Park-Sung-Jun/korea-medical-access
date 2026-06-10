"""
SGIS(통계지리정보서비스) 통계주제도 — '건강과 안전'(CTGR_005) 취득.

목적: 정부 공식 의료기관 접근성 지표를 시군구 단위로 받아
      우리 ORS(자유흐름)/TMAP(교통) 접근성의 3번째 독립 벤치마크로 사용.

키: .env 의 SGIS_CONSUMER_KEY(서비스ID) / SGIS_CONSUMER_SECRET(보안Key)  → accessToken(4h)

usage:
  python scripts/fetch_sgis.py list                       # CTGR_005 통계주제도 목록(제목+id) 출력
  python scripts/fetch_sgis.py data <stat_thema_map_id>   # 해당 지표 시군구(region_div=2) CSV 저장
  python scripts/fetch_sgis.py data <id> --year 2023
"""
import argparse
import csv
import os
from pathlib import Path

import requests
import _env  # noqa: F401  (.env 자동 로드 side-effect)

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
BASE = "https://sgisapi.mods.go.kr/OpenAPI3"


def get_token():
    ck = os.environ.get("SGIS_CONSUMER_KEY", "").strip()
    cs = os.environ.get("SGIS_CONSUMER_SECRET", "").strip()
    if not ck or not cs:
        raise SystemExit("SGIS_CONSUMER_KEY / SGIS_CONSUMER_SECRET (.env) 가 필요합니다.")
    r = requests.get(f"{BASE}/auth/authentication.json",
                     params={"consumer_key": ck, "consumer_secret": cs}, timeout=30)
    r.raise_for_status()
    j = r.json()
    if str(j.get("errCd")) not in ("0", "None") and j.get("errCd") not in (0, None):
        raise SystemExit(f"인증 실패: {j.get('errCd')} {j.get('errMsg')}")
    return j["result"]["accessToken"]


def list_maps(token, ctgr="CTGR_005"):
    r = requests.get(f"{BASE}/themamap/{ctgr}/list.json",
                     params={"accessToken": token}, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j.get("result", [])


def fetch_data(token, map_id, region_div=2, adm_cd="00", year=None, ctgr="CTGR_005"):
    params = {"accessToken": token, "stat_thema_map_id": map_id,
              "region_div": region_div, "adm_cd": adm_cd}
    if year:
        params["year"] = year
    r = requests.get(f"{BASE}/themamap/{ctgr}/data.json", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def cmd_list(args):
    token = get_token()
    maps = list_maps(token, args.ctgr)
    print(f"[{args.ctgr}] 통계주제도 {len(maps)}건")
    for m in maps:
        # 키 이름은 응답에 따라 다를 수 있어 안전하게 추출
        mid = m.get("stat_thema_map_id") or m.get("statThemaMapId") or "?"
        title = (m.get("title") or m.get("stat_thema_map_title")
                 or m.get("themaMapTitle") or m.get("map_nm") or "?")
        acc = "★접근성" if ("접근" in str(title) or "의료" in str(title)) else ""
        print(f"  {mid}  {title} {acc}")
    # 원본 한 건 구조 확인용
    if maps:
        print("\n[sample keys]", list(maps[0].keys()))


def cmd_data(args):
    token = get_token()
    j = fetch_data(token, args.map_id, args.region_div, args.adm_cd, args.year, args.ctgr)
    rows = j.get("result", [])
    if not rows:
        print("결과 0건. 응답:", {k: j.get(k) for k in ("errCd", "errMsg", "id")})
        print("keys:", list(j.keys()))
        return
    keys = list(rows[0].keys())
    out = DATA / f"sgis_{args.map_id[:16]}_div{args.region_div}.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"저장: {out}  (rows={len(rows)})")
    print("컬럼:", keys)
    print("샘플:", rows[0])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list")
    pl.add_argument("--ctgr", default="CTGR_005")
    pd = sub.add_parser("data")
    pd.add_argument("map_id")
    pd.add_argument("--region_div", type=int, default=2)  # 1시도 2시군구 3읍면동
    pd.add_argument("--adm_cd", default="00")
    pd.add_argument("--year", default=None)
    pd.add_argument("--ctgr", default="CTGR_005")
    args = ap.parse_args()
    {"list": cmd_list, "data": cmd_data}[args.cmd](args)


if __name__ == "__main__":
    main()

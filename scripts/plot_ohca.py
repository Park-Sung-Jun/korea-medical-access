"""
시도 단위 산점도 2종:
  (1) 상급종합 사각지대비율 vs OHCA 질병성 표준화 생존율
  (2) 고령화지수(시도평균) vs OHCA 질병성 표준화 생존율
저장된 data/ohca_survival_sido.csv + sigungu_bivariate.geojson 로 그린다(API 키 불필요).
출력: charts/ohca_scatter.png
"""
import csv
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fetch_ohca import sido_access_metrics, latest_by_sido, find_col, BIV  # noqa: E402

DATA = HERE.parent / "data"
OUT = HERE.parent / "charts"
OUT.mkdir(exist_ok=True)

# 한글 폰트(Windows)
for f in ["Malgun Gothic", "AppleGothic", "NanumGothic"]:
    try:
        plt.rcParams["font.family"] = f
        break
    except Exception:
        pass
plt.rcParams["axes.unicode_minus"] = False

SHORT = {  # 라벨용 짧은 시도명
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전라북도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주",
}


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs) ** 0.5
    syy = sum((y - my) ** 2 for y in ys) ** 0.5
    return sxy / (sxx * syy)


def load_survival():
    rows = list(csv.DictReader((DATA / "ohca_survival_sido.csv").open(encoding="utf-8-sig")))
    latest, ks = latest_by_sido(rows)
    col = find_col(ks, "질병_표준")
    return {sido: float(r[col]) for sido, (yr, r) in latest.items() if r.get(col)}


def panel(ax, xs, ys, labels, xlabel, hi_idx, title):
    xs, ys = np.array(xs), np.array(ys)
    # 추세선
    b, a = np.polyfit(xs, ys, 1)
    xr = np.linspace(xs.min(), xs.max(), 50)
    ax.plot(xr, a + b * xr, color="#9ca3af", lw=1.2, zorder=1)
    # 점
    colors = ["#dc2626" if i in hi_idx else "#111111" for i in range(len(xs))]
    ax.scatter(xs, ys, c=colors, s=46, zorder=3, edgecolor="#ffffff", linewidth=0.8)
    for x, y, t in zip(xs, ys, labels):
        ax.annotate(t, (x, y), xytext=(4, 4), textcoords="offset points",
                    fontsize=8.5, color="#374151")
    r = pearson(list(xs), list(ys))
    ax.set_title(f"{title}\nPearson r = {r:+.3f}", fontsize=11, loc="left")
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel("OHCA 질병성 표준화 생존율 (%)", fontsize=10)
    ax.grid(True, color="#eef0f2", lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#d1d5db")


def main():
    acc = sido_access_metrics(BIV)
    surv = load_survival()
    sidos = [s for s in acc if s in surv]

    dead = [acc[s]["deadzone_share"] * 100 for s in sidos]
    aging = [acc[s]["mean_aging"] for s in sidos]
    y = [surv[s] for s in sidos]
    labels = [SHORT.get(s, s) for s in sidos]
    jeju = [i for i, s in enumerate(sidos) if s == "제주특별자치도"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.2))
    fig.suptitle("시도 단위 검증 — 상급종합 접근성·고령화 vs 급성심장정지 생존율 (2023, n=17)",
                 fontsize=12.5, x=0.01, ha="left", weight="bold")
    panel(ax1, dead, y, labels, "상급종합 60분초과(사각지대) 시군구 비율 (%)", jeju,
          "① 접근성 사각지대 vs 생존율")
    panel(ax2, aging, y, labels, "고령화지수 (시도 평균)", jeju,
          "② 고령화 vs 생존율")
    fig.text(0.01, 0.005, "● 검정 = 시도, ● 빨강 = 제주(섬·접근성 과대추정)  |  회색선 = 선형추세",
             fontsize=8.5, color="#6b7280")
    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    out = OUT / "ohca_scatter.png"
    fig.savefig(out, dpi=150, facecolor="white")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()

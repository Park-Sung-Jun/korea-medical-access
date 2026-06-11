# -*- coding: utf-8 -*-
"""합성 건강검진 데이터 대시보드 서버 (표준 라이브러리만 사용).

  python synthetic/server.py            # http://localhost:8081
  python synthetic/server.py --port 8082

엔드포인트
  GET  /                → synthetic/ 정적 파일(대시보드)
  GET  /api/health      → 헬스체크
  GET  /api/meta        → 시도 목록·상태(세션별)
  POST /api/generate    → 합성데이터 생성 {n, sido, seed, corr}
  GET  /api/download    → ?type=a|b|c CSV 다운로드(세션별)

배포(다중 사용자) 주의
  - 생성 결과는 사용자별로 격리한다. 사용자 식별은 oauth2-proxy가 넘기는
    `X-Auth-Request-Email` 헤더(또는 Cf-Access-* / X-Forwarded-*)를 쓰며,
    없으면 단일 'default' 세션이 된다(로컬·단독 사용).
  - 외부 노출은 nginx+oauth2-proxy 뒤에 두고 앱은 127.0.0.1만 바인드한다
    (DEPLOY.md 표준). 대용량(50만 행) 생성은 수 분 걸리므로 nginx
    proxy_read_timeout을 600s로 올린다. 환경변수로 제어:
      SYNTH_HOST(기본 127.0.0.1) · SYNTH_PORT(8081) · SYNTH_MAX_N(500000)
      SYNTH_SESSION_MAX(16) · SYNTH_SESSION_MB(총 세션 메모리 상한, 기본 512)
      SYNTH_TRUST_PROXY(1이면 X-Forwarded-* 신뢰)
  - 세션에는 행 객체가 아니라 직렬화된 CSV 문자열을 저장한다(50만 행 기준
    행 dict ~600MB → CSV ~70MB). 총량이 SYNTH_SESSION_MB를 넘으면 LRU 제거.
"""

import argparse
import csv
import io
import json
import os
import sys
import threading
import time
import zipfile
from collections import OrderedDict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import generator  # noqa: E402

MAX_N = int(os.environ.get("SYNTH_MAX_N", str(generator.MAX_ROWS)))
SESSION_MAX = int(os.environ.get("SYNTH_SESSION_MAX", "16"))
SESSION_MB = int(os.environ.get("SYNTH_SESSION_MB", "512"))
TRUST_PROXY = os.environ.get("SYNTH_TRUST_PROXY", "0") == "1"

# 사용자(세션) 키 → {"csv_a","b","c","meta","bytes"} — 개수·총바이트 LRU
_SESSIONS = OrderedDict()
_LOCK = threading.Lock()
_GEN_BUSY = threading.Lock()

SPEC = None  # main()에서 채움(기본/최신 연도)
_SPECS = {}  # year -> spec (연도별 지연 로드 캐시). None 키 = 기본(최신)
_SPEC_LOCK = threading.Lock()

# 정적 서빙 화이트리스트 — 이 외 경로(.py/.md 등 소스)는 404
STATIC_WHITELIST = {"/", "/index.html", "/app.js", "/styles.css", "/favicon.ico"}


def _decode_csv(csv_bytes):
    """세션 저장 CSV(UTF-8 bytes) → DictReader 행 리스트 + 헤더."""
    text = (csv_bytes or b"").decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), (reader.fieldnames or [])


def _project_csv(csv_bytes, cols):
    """캐시 A안 CSV에서 요청 컬럼만 추린 CSV 문자열 반환(화이트리스트 교집합)."""
    rows, header = _decode_csv(csv_bytes)
    fields = generator._project_cols(cols)
    fields = [c for c in fields if c in header] or header
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    return buf.getvalue()


def _csv_to_json(csv_bytes):
    """캐시 A안 CSV → JSON 배열(UTF-8 bytes). 숫자형은 가능한 경우 숫자로 변환."""
    rows, _ = _decode_csv(csv_bytes)

    def _coerce(v):
        if v == "":
            return None
        try:
            f = float(v)
            return int(f) if f.is_integer() else f
        except ValueError:
            return v
    out = [{k: _coerce(v) for k, v in r.items()} for r in rows]
    return json.dumps(out, ensure_ascii=False).encode("utf-8")


def _get_spec(year=None):
    """연도별 스펙 반환(캐시). 캐시/원본 없으면 ValueError로 사용자에게 전달."""
    if year is None:
        return SPEC
    with _SPEC_LOCK:
        if year in _SPECS:
            return _SPECS[year]
    # load_spec은 디스크 캐시 우선, 없으면 빌드(CSV 필요). 배포엔 캐시만 존재.
    spec = generator.load_spec(year=year)
    with _SPEC_LOCK:
        _SPECS[year] = spec
    return spec


def _store_session(key, data):
    # csv_a는 UTF-8 bytes로 저장 — 메모리 계량이 정확하고 다운로드 시 재인코딩 없음
    data["bytes"] = len(data.get("csv_a") or b"")
    with _LOCK:
        _SESSIONS[key] = data
        _SESSIONS.move_to_end(key)
        total = sum(d["bytes"] for d in _SESSIONS.values())
        while len(_SESSIONS) > 1 and (
                len(_SESSIONS) > SESSION_MAX or total > SESSION_MB * 1_000_000):
            _k, dropped = _SESSIONS.popitem(last=False)
            total -= dropped["bytes"]


def _get_session(key):
    with _LOCK:
        d = _SESSIONS.get(key)
        if d is not None:
            _SESSIONS.move_to_end(key)
        return d


def _load_spec_once():
    """기본(최신) 스펙 로드 + 부팅 정합성 검증. 깨진 baseline은 즉시 종료(명확한 안내)."""
    t0 = time.time()
    try:
        spec = generator.load_spec()
    except FileNotFoundError as e:
        sys.exit(f"[server] 치명: 스펙 빌드 실패(KOSIS CSV 없음). "
                 f"로컬에서 'python synthetic/generator.py --build-all-years' 후 "
                 f"data/synthetic_baseline*.json 을 배포하세요. ({e})")
    # 정합성 가드 — sigungu/demo_joint 누락이면 시군구·생성이 런타임에 깨진다
    problems = []
    if spec.get("spec_version") != generator.SPEC_VERSION:
        problems.append(f"spec_version={spec.get('spec_version')}≠{generator.SPEC_VERSION}")
    if len(spec.get("sigungu") or {}) < 200:
        problems.append(f"sigungu={len(spec.get('sigungu') or {})}<200")
    if not spec.get("demo_joint"):
        problems.append("demo_joint 누락")
    if problems:
        sys.exit("[server] 치명: baseline 정합성 실패 — " + ", ".join(problems)
                 + ". --build-all-years 로 재빌드 후 배포하세요.")
    print(f"[server] 스펙 로드 완료 {spec.get('year')}년 {time.time() - t0:.1f}s "
          f"· 연도 {generator.cached_years()} · 시군구 {len(spec.get('sigungu') or {})}")
    return spec


class Handler(SimpleHTTPRequestHandler):
    timeout = 60  # 유휴/지연 소켓 차단 — 본문 미전송 클라이언트의 스레드 영구 점유 방지

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    # ---- 세션 식별
    def _session_key(self):
        # 인증 프록시가 넘긴 이메일로 사용자별 데이터 격리.
        # oauth2-proxy(X-Auth-Request-Email / X-Forwarded-Email) 또는
        # Cloudflare Access(Cf-Access-Authenticated-User-Email)를 지원한다.
        # 헤더 위조 방지를 위해 프록시 주입 헤더는 전부 TRUST_PROXY=1일 때만
        # 신뢰한다(앱은 127.0.0.1만 바인드하고 외부 포트를 열지 않는 전제).
        if TRUST_PROXY:
            email = (self.headers.get("X-Auth-Request-Email")
                     or self.headers.get("X-Forwarded-Email")
                     or self.headers.get("X-Forwarded-User")
                     or self.headers.get("Cf-Access-Authenticated-User-Email"))
            if email:
                return "u:" + email.strip().lower()
        return "default"

    # ---- 공통 응답 헬퍼
    def end_headers(self):
        # 모든 응답(정적·API·에러)에 기본 보안 헤더 주입
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        # CSP: 자체 호스팅 자산만 사용(외부 CDN 없음). 인라인 스크립트 없음(app.js 분리).
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'self'")
        super().end_headers()

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _csv(self, data, filename):
        """CSV 응답(엑셀 호환 UTF-8 BOM). data는 str 또는 bytes.

        BOM과 본문을 분리 전송해 대용량 CSV의 concat 사본(순간 2배 메모리)을 만들지 않는다."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(3 + len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b"\xef\xbb\xbf")
        self.wfile.write(data)

    def _bytes(self, data, ctype, filename):
        """임의 바이트 첨부 다운로드(JSON·ZIP 등)."""
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _batch_zip(self, d):
        """시드 배치 replicate ZIP — 같은 조건에서 seed를 1,2,…로 바꾼 복제본 + 데이터카드."""
        opt = d.get("opt") or {}
        reps = max(1, min(int(opt.get("replicates") or 1), 50))
        base_seed = d["meta"].get("seed") or 1
        spec = _get_spec(opt.get("year"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(reps):
                seed_i = base_seed + i
                rows, meta = generator.generate(
                    spec, opt.get("n") or 10000,
                    sido=opt.get("sido") or "전체", seed=seed_i, corr=opt.get("corr", 1.0),
                    sigungu=opt.get("sigungu"), age_min=opt.get("age_min"),
                    age_max=opt.get("age_max"), sex=opt.get("sex"),
                    missing=opt.get("missing"), anchor=opt.get("anchor", "cr"))
                zf.writestr(f"replicate_{i + 1:02d}_seed{seed_i}.csv",
                            b"\xef\xbb\xbf" + generator.rows_to_csv(rows).encode("utf-8"))
                zf.writestr(f"replicate_{i + 1:02d}_datacard.json",
                            json.dumps(generator.build_datacard(meta),
                                       ensure_ascii=False, indent=2))
                del rows
        return self._bytes(buf.getvalue(), "application/zip",
                           "synthetic_health_batch.zip")

    def log_message(self, fmt, *args):  # 콘솔 소음 축소
        # 에러 로깅 경로(log_error)는 args[0]이 HTTPStatus 등 비문자열일 수 있다.
        first = args[0] if args else ""
        if not isinstance(first, str) or "/api/" in first:
            super().log_message(fmt, *args)

    # ---- 라우팅
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            # 운영 모니터링용 심화: 스펙 로드 여부·연도·시군구 수·세션 수
            years = generator.cached_years()
            return self._json({
                "ok": True, "status": "healthy" if SPEC else "degraded",
                "year": (SPEC or {}).get("year", generator.LATEST_YEAR),
                "spec_version": (SPEC or {}).get("spec_version"),
                "spec_loaded": SPEC is not None,
                "sigungu_count": len((SPEC or {}).get("sigungu") or {}),
                "years_available": years,
                "max_n": MAX_N, "sessions": len(_SESSIONS),
            })
        if parsed.path == "/api/meta":
            d = _get_session(self._session_key())
            meta = d["meta"] if d else None
            years = generator.cached_years()
            default_year = (SPEC or {}).get("year", generator.LATEST_YEAR)
            return self._json({
                "ok": True,
                "sidos": ["전체"] + list(generator.SIDOS),
                "sigungu_map": generator.list_sigungu(SPEC) if SPEC else {},
                "year": default_year,
                "years": years or [default_year],
                "default_year": default_year,
                "grade_desc": generator.GRADE_DESC,
                "corr_presets": generator.CORR_PRESETS,
                "has_data": meta is not None,
                "max_n": MAX_N,
                "last_meta": meta,
            })
        if parsed.path == "/api/download":
            qs = parse_qs(parsed.query)
            typ = (qs.get("type") or ["a"])[0].lower()
            cols = (qs.get("cols") or [None])[0]
            d = _get_session(self._session_key())
            if not d:
                return self._json({"ok": False, "error": "생성된 데이터가 없습니다. 먼저 생성하세요."}, 404)
            if typ == "a":
                if cols:  # 컬럼 프로젝션 — 캐시 CSV를 재파싱해 부분집합 생성
                    return self._csv(_project_csv(d["csv_a"], cols),
                                     "synthetic_health_a_subset.csv")
                return self._csv(d["csv_a"], "synthetic_health_a_individual.csv")
            if typ == "b":
                return self._csv(generator.dicts_to_csv(d["b"], generator.B_FIELDS),
                                 "synthetic_health_b_summary.csv")
            if typ == "c":
                return self._csv(generator.dicts_to_csv(d["c"], generator.C_FIELDS),
                                 "synthetic_health_c_risk_matrix.csv")
            if typ == "card":  # 데이터카드(provenance JSON)
                card = generator.build_datacard(d["meta"])
                return self._bytes(json.dumps(card, ensure_ascii=False, indent=2)
                                   .encode("utf-8"), "application/json; charset=utf-8",
                                   "synthetic_health_datacard.json")
            if typ == "json":  # A안 JSON(캐시 CSV 재파싱)
                return self._bytes(_csv_to_json(d["csv_a"]), "application/json; charset=utf-8",
                                   "synthetic_health_a_individual.json")
            if typ == "batch":  # 시드 배치 replicate ZIP
                return self._batch_zip(d)
            return self._json({"ok": False, "error": "type은 a|b|c|card|json|batch 중 하나여야 합니다."}, 400)
        if parsed.path.startswith("/api/"):
            return self._json({"ok": False, "error": "알 수 없는 API"}, 404)
        # 정적 파일은 프론트 자산만 화이트리스트로 노출. server.py/generator.py/
        # DEPLOY.md 등 소스·문서가 인증 사용자에게 다운로드되는 것을 차단(정찰정보 노출 방지).
        if parsed.path not in STATIC_WHITELIST:
            return self._json({"ok": False, "error": "찾을 수 없습니다."}, 404)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/generate":
            return self._json({"ok": False, "error": "알 수 없는 API"}, 404)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not (0 <= length <= 1_000_000):
                # 음수 길이는 rfile.read(-1)이 EOF까지 블록하므로 read 전에 차단
                return self._json({"ok": False, "error": "요청 본문 크기가 올바르지 않습니다."}, 400)
            payload = json.loads(self.rfile.read(length) or b"{}")
            opt = self._parse_gen_opts(payload)
        except (ValueError, TypeError, json.JSONDecodeError):
            return self._json({"ok": False, "error": "요청 형식이 올바르지 않습니다."}, 400)

        if not (100 <= opt["n"] <= MAX_N):
            return self._json({"ok": False, "error": f"표본 수는 100~{MAX_N:,} 범위여야 합니다."}, 400)
        if opt["replicates"] > 1 and opt["n"] * opt["replicates"] > MAX_N * 4:
            return self._json({"ok": False, "error": "배치 총량이 너무 큽니다(표본수×반복 ≤ 상한×4)."}, 400)

        if not _GEN_BUSY.acquire(blocking=False):
            return self._json({"ok": False, "error": "이미 생성 작업이 진행 중입니다. 잠시 후 다시 시도하세요."}, 429)
        # 락 구간은 생성→집계→세션 저장까지만. 응답 직렬화·소켓 전송은 락 해제 후
        # 수행한다(느린 수신 클라이언트가 전역 생성 락을 점유하는 것 방지).
        try:
            resp, status = self._do_generate(opt)
        except ValueError as e:
            resp, status = {"ok": False, "error": str(e)}, 400
        except Exception as e:  # noqa: BLE001 — 사용자에게 원인 전달
            resp, status = {"ok": False, "error": f"생성 실패: {e}"}, 500
        finally:
            _GEN_BUSY.release()
        try:
            return self._json(resp, status)
        except (ConnectionError, BrokenPipeError):
            return  # 클라이언트가 응답 전송 중 끊음 — 재전송 시도 안 함

    @staticmethod
    def _parse_gen_opts(payload):
        """generate 파라미터 파싱·정규화(검증은 generator/상위에서 ValueError로)."""
        def _int_or_none(v):
            return int(v) if v not in (None, "") else None
        seed = payload.get("seed")
        return {
            "n": int(payload.get("n") or 10000),
            "sido": str(payload.get("sido") or "전체"),
            "sigungu": str(payload.get("sigungu") or "").strip() or None,
            "seed": _int_or_none(seed),
            "corr": float(payload.get("corr") if payload.get("corr") is not None else 1.0),
            "year": _int_or_none(payload.get("year")),
            "age_min": _int_or_none(payload.get("age_min")),
            "age_max": _int_or_none(payload.get("age_max")),
            "sex": str(payload.get("sex")).strip() or None if payload.get("sex") else None,
            "anchor": str(payload.get("anchor") or "cr"),
            "missing": payload.get("missing") or None,
            "replicates": max(1, min(int(payload.get("replicates") or 1), 50)),
        }

    def _do_generate(self, opt):
        """생성+검증 리포트 일괄 수행(_GEN_BUSY 락 하에서 호출). 반환: (응답 dict, 상태코드)."""
        spec = _get_spec(opt["year"])
        rows, meta = generator.generate(
            spec, opt["n"], sido=opt["sido"], seed=opt["seed"], corr=opt["corr"],
            sigungu=opt["sigungu"], age_min=opt["age_min"], age_max=opt["age_max"],
            sex=opt["sex"], missing=opt["missing"], anchor=opt["anchor"])
        sido = opt["sido"]
        sigungu = opt["sigungu"]
        b = generator.summary_b(rows)
        c = generator.matrix_c(rows)
        ver = generator.verify_report(spec, rows)
        demo = generator.demographic_verify(spec, rows, sido, sigungu=sigungu)
        fidelity = generator.fidelity_breakdown(spec, rows)
        privacy = generator.privacy_report(rows)
        gc = generator.grade_compare(spec, rows)
        sido_cmp = generator.sido_risk_compare(spec, rows)
        grade_cnt = {g: 0 for g in generator.GRADE_CATS}
        for r in rows:
            grade_cnt[r["result_grade"]] += 1
        kpi = {
            "rows": len(rows),
            "elapsed_ms": meta["elapsed_ms"],
            # 헤드라인은 대외 충실도(KOSIS 원시 전국 대비), 내부 정합성은 보조
            "mean_abs_diff_pct": generator.mean_abs_diff(ver, "raw_kosis_pct"),
            "mean_abs_diff_internal_pct": generator.mean_abs_diff(ver, "kosis_pct"),
            "grade_dist": {g: round(grade_cnt[g] * 100.0 / len(rows), 1)
                           for g in generator.GRADE_CATS},
        }
        preview = rows[:200]
        # 세션엔 UTF-8 bytes CSV만 저장(대용량 행 객체 장기 보유 방지 + 정확한 계량)
        csv_a = generator.rows_to_csv(rows).encode("utf-8")
        del rows
        # 배치(replicate)는 다운로드 시 재생성(시드+1,2,...) — 옵션만 보관
        _store_session(self._session_key(),
                       {"csv_a": csv_a, "meta": meta, "b": b, "c": c, "opt": opt})
        return {
            "ok": True, "meta": meta, "kpi": kpi,
            "preview": preview,
            "summary_b": b, "matrix_c": c,
            "verify": ver, "grade_compare": gc,
            "demographics": demo, "fidelity": fidelity, "privacy": privacy,
            "sido_compare": sido_cmp,
        }, 200


def main():
    global SPEC
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("SYNTH_PORT", "8081")))
    ap.add_argument("--host", default=os.environ.get("SYNTH_HOST", "127.0.0.1"))
    args = ap.parse_args()
    SPEC = _load_spec_once()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[server] http://{args.host}:{args.port}  (Ctrl+C로 종료)")
    print(f"[server] MAX_N={MAX_N:,} · SESSION_MAX={SESSION_MAX} · TRUST_PROXY={TRUST_PROXY}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] 종료")


if __name__ == "__main__":
    main()

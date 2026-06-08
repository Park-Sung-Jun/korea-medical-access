"""프로젝트 루트의 .env 를 os.environ 으로 로드(이미 설정된 값은 보존). import 만으로 동작."""
import os
from pathlib import Path


def load(path=None):
    p = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:   # 이미 설정된 환경변수가 우선
            os.environ[k] = v


load()

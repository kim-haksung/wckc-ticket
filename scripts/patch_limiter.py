#!/usr/bin/env python3
"""
patch_limiter.py
================
Flask-Limiter 로그인 제한 패치 (10회/분)
- app.py 에 Limiter 초기화, @limiter.limit 데코레이터, 429 핸들러 추가
- start_server.py 의 REQUIRED 목록에 flask-limiter 추가
- 기존 기능 전혀 변경 없음
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP  = ROOT / 'app.py'
SRV  = ROOT / 'start_server.py'

# ── 패치 적용 헬퍼 ──────────────────────────────────────────────────
def patch(path: Path, old: str, new: str, label: str) -> bool:
    src = path.read_text(encoding='utf-8')
    if old not in src:
        print(f"  [SKIP] {label}  (이미 적용됨)")
        return False
    path.write_text(src.replace(old, new, 1), encoding='utf-8')
    print(f"  [PATCH] {label}")
    return True

print("=" * 55)
print("  Flask-Limiter 로그인 제한 패치")
print("=" * 55)

# ────────────────────────────────────────────────────────────────────
# [A] start_server.py — flask-limiter 를 REQUIRED 목록에 추가
# ────────────────────────────────────────────────────────────────────
patch(
    SRV,
    "REQUIRED = ['flask', 'openpyxl', 'waitress', 'werkzeug']",
    "REQUIRED = ['flask', 'openpyxl', 'waitress', 'werkzeug', 'flask-limiter']",
    "start_server.py: REQUIRED에 flask-limiter 추가"
)

# ────────────────────────────────────────────────────────────────────
# [B] app.py — import 추가 (werkzeug import 줄 바로 뒤)
# ────────────────────────────────────────────────────────────────────
patch(
    APP,
    "from werkzeug.security import generate_password_hash, check_password_hash",
    (
        "from werkzeug.security import generate_password_hash, check_password_hash\n"
        "from flask_limiter import Limiter\n"
        "from flask_limiter.util import get_remote_address"
    ),
    "app.py: Flask-Limiter import 추가"
)

# ────────────────────────────────────────────────────────────────────
# [C] app.py — Limiter 초기화 (JSON_AS_ASCII 설정 바로 뒤)
# ────────────────────────────────────────────────────────────────────
patch(
    APP,
    "app.config['JSON_AS_ASCII']             = False   # 한글 JSON 인코딩 최적화",
    (
        "app.config['JSON_AS_ASCII']             = False   # 한글 JSON 인코딩 최적화\n"
        "\n"
        "# ── Flask-Limiter: 로그인 무차별 대입 공격 방어 ─────────────────────\n"
        "# - 메모리 저장소 사용 (Redis 불필요, 서버 재시작 시 카운터 초기화)\n"
        "# - 기본 제한 없음 (로그인 라우트에만 @limiter.limit 으로 개별 적용)\n"
        "limiter = Limiter(\n"
        "    app=app,\n"
        "    key_func=get_remote_address,  # IP 기준 카운팅\n"
        "    default_limits=[],            # 전역 제한 없음 — 로그인에만 적용\n"
        "    storage_uri='memory://',\n"
        ")"
    ),
    "app.py: Limiter 초기화 블록 추가"
)

# ────────────────────────────────────────────────────────────────────
# [D] app.py — /api/login 라우트에 @limiter.limit 데코레이터 추가
# ────────────────────────────────────────────────────────────────────
patch(
    APP,
    "@app.route('/api/login', methods=['POST'])\ndef login():",
    (
        "@app.route('/api/login', methods=['POST'])\n"
        "@limiter.limit('10 per minute')   # 같은 IP에서 1분에 10회 초과 시 429\n"
        "def login():"
    ),
    "app.py: /api/login 에 @limiter.limit('10 per minute') 추가"
)

# ────────────────────────────────────────────────────────────────────
# [E] app.py — 429 에러를 JSON 형식으로 반환하는 핸들러 추가
#     (logout 라우트 바로 위에 삽입)
# ────────────────────────────────────────────────────────────────────
patch(
    APP,
    "@app.route('/api/logout', methods=['POST'])",
    (
        "# ── 429 Rate-Limit 에러 → JSON 응답 (HTML 대신) ─────────────────────\n"
        "@app.errorhandler(429)\n"
        "def too_many_requests(e):\n"
        "    return jsonify({'error': '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.'}), 429\n"
        "\n"
        "@app.route('/api/logout', methods=['POST'])"
    ),
    "app.py: 429 JSON 에러 핸들러 추가"
)

# ────────────────────────────────────────────────────────────────────
# 최종 검증
# ────────────────────────────────────────────────────────────────────
print()
src = APP.read_text(encoding='utf-8')
checks = [
    ("flask-limiter import",      "from flask_limiter import Limiter"),
    ("Limiter 초기화",             "limiter = Limiter("),
    ("@limiter.limit 데코레이터",  "@limiter.limit('10 per minute')"),
    ("429 핸들러",                 "@app.errorhandler(429)"),
    ("REQUIRED flask-limiter",    "'flask-limiter'"),
]
all_ok = True
for label, keyword in checks:
    found = keyword in src
    print(f"  {'✓' if found else '✗'} {label}")
    if not found:
        all_ok = False

srv_src = SRV.read_text(encoding='utf-8')
found = "'flask-limiter'" in srv_src
print(f"  {'✓' if found else '✗'} start_server.py REQUIRED")
if not found:
    all_ok = False

print()
if all_ok:
    print("  ✅ 모든 패치 적용 완료")
else:
    print("  ❌ 일부 패치 실패 — 위 항목 확인 필요")
    sys.exit(1)

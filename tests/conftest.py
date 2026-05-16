"""
테스트 하네스 공통 pytest 픽스처 (conftest.py)
헬퍼 함수는 tests/helpers.py 에 위치
"""
# ── [안정성] virtiofs 1초 mtime 해상도로 인한 stale .pyc 방지 ────
# virtiofs(Windows↔Linux 마운트)는 mtime 해상도가 1초 단위여서
# 같은 초 안에 파일이 두 번 쓰이면 Python이 old .pyc를 재사용함.
# dont_write_bytecode=True 로 pyc 생성/읽기를 런타임에서도 차단.
import sys
sys.dont_write_bytecode = True

import os
import time
import uuid
import pytest

# ── sys.path 설정 ─────────────────────────────────────────────
_root = os.path.dirname(os.path.dirname(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# ── 환경 변수 설정 (app 임포트 전) ────────────────────────────
import tempfile
_tmp = tempfile.NamedTemporaryFile(suffix="_harness.db", delete=False)
_tmp.close()
os.environ.setdefault("TICKET_DB", _tmp.name)
os.environ.setdefault("SECRET_KEY", "test-harness-secret-key-do-not-use-in-prod")

import app as _app
from app import app as flask_app
from tests.helpers import (
    inject_session, inject_queue_token, create_db_user, TEST_CSRF
)


# ======================== session scope ==========================
@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    _app._init_db_done = False
    _app.init_db()
    yield
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(_tmp.name + ext)
        except FileNotFoundError:
            pass


# ======================== function scope =========================
@pytest.fixture(autouse=True)
def reset_queue_state():
    with _app._ql:
        _app._active.clear()
        _app._waiting.clear()
    yield
    with _app._ql:
        _app._active.clear()
        _app._waiting.clear()


@pytest.fixture(autouse=True)
def clean_db_data():
    conn = _app.get_db()
    conn.execute("DELETE FROM reservations")
    conn.execute(
        "UPDATE seats SET status='available', locked_by=NULL, locked_at=NULL"
    )
    conn.execute("DELETE FROM users WHERE username != 'admin'")
    conn.commit()
    conn.close()
    yield


# ======================== pytest 훅: 수집 전 구문 검증 ==========
def pytest_collect_file(parent, file_path):
    """
    [안정성 훅] 각 테스트 파일을 수집하기 전에 AST 구문 검증 실행.
    - virtiofs + bash heredoc 조합으로 파일이 중간에 잘리는 경우 감지
    - 잘린 파일이 pytest에 들어오면 SyntaxError 대신 명확한 에러 출력
    """
    if file_path.suffix == ".py" and file_path.name.startswith("test_"):
        import ast
        try:
            source = file_path.read_text(encoding="utf-8")
            ast.parse(source)
        except SyntaxError as e:
            raise RuntimeError(
                f"\n[파일 손상 감지] {file_path.name} 구문 오류:\n"
                f"  {e.msg} (line {e.lineno})\n"
                f"  → bash heredoc 으로 한국어 파일을 쓰지 마십시오.\n"
                f"  → python3 open(..., encoding='utf-8').write(...) 를 사용하세요."
            ) from e


# ======================== base fixtures ==========================
@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


# ======================== role fixtures ==========================
@pytest.fixture
def test_user_id():
    return create_db_user("harness_user", name="하네스테스터")


@pytest.fixture
def auth_client(client, test_user_id):
    inject_session(client, test_user_id, "harness_user", "하네스테스터")
    token = inject_queue_token(test_user_id, "하네스테스터")
    client._queue_token = token
    client._user_id = test_user_id   # ← user_id 정수도 첨부
    return client


@pytest.fixture
def admin_client(client):
    conn = _app.get_db()
    admin = conn.execute(
        "SELECT id FROM users WHERE username='admin'"
    ).fetchone()
    conn.close()
    inject_session(client, admin["id"], "admin", "관리자", role="admin")
    token = inject_queue_token(admin["id"], "관리자")
    client._queue_token = token
    client._user_id = admin["id"]
    return client

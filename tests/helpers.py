"""
테스트 하네스 공통 헬퍼 함수
test_*.py 에서 `from tests.helpers import ...` 로 사용
"""
import os
import sys
import time
import uuid

# tests/ 디렉토리 기준으로 ticket-system 루트를 sys.path에 추가
_root = os.path.dirname(os.path.dirname(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# ── 환경 변수 설정 (app 임포트 전) ────────────────────────────
import tempfile
_tmp = tempfile.NamedTemporaryFile(suffix='_harness.db', delete=False)
_tmp.close()
os.environ.setdefault('TICKET_DB', _tmp.name)
os.environ.setdefault('SECRET_KEY', 'test-harness-secret-key-do-not-use-in-prod')

import app as _app

# ── 공통 상수 ────────────────────────────────────────────────
TEST_CSRF = 'test-csrf-token-harness-2026'
SEAT_1F   = '가001'
SEAT_2F   = '사001'


def get_csrf(client):
    """서버에서 CSRF 토큰 발급"""
    return client.get('/api/csrf-token').get_json()['csrf_token']


def h(client):
    """POST/PUT/DELETE 헤더 (CSRF + Content-Type)"""
    return {
        'X-CSRF-Token': get_csrf(client),
        'Content-Type': 'application/json',
    }


def inject_session(client, user_id, username, name, role='user'):
    """Flask 세션에 로그인 정보 직접 주입"""
    with client.session_transaction() as sess:
        sess['user_id']    = user_id
        sess['username']   = username
        sess['name']       = name
        sess['role']       = role
        sess['csrf_token'] = TEST_CSRF


def inject_queue_token(user_id, name):
    """_active 대기열에 토큰 직접 주입"""
    token = str(uuid.uuid4())
    with _app._ql:
        _app._active[token] = {
            'uid':        user_id,
            'name':       name,
            'entered_at': time.time(),
            'heartbeat':  time.time(),
        }
    return token


def create_db_user(username, name='테스터', phone='010-0000-0000',
                   church='테스트교회', position='성도', role='user'):
    """DB에 사용자를 직접 생성하고 id 반환"""
    conn = _app.get_db()
    conn.execute(
        "INSERT INTO users (username, password, name, phone, church, position, role) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (username, _app.hash_password('Test1234!'),
         name, phone, church, position, role)
    )
    conn.commit()
    uid = conn.execute(
        "SELECT id FROM users WHERE username=?", (username,)
    ).fetchone()['id']
    conn.close()
    return uid


def api_post(client, path, data):
    return client.post(path, json=data,
                       headers={'X-CSRF-Token': TEST_CSRF,
                                'Content-Type': 'application/json'})


def api_delete(client, path):
    return client.delete(path,
                         headers={'X-CSRF-Token': TEST_CSRF,
                                  'Content-Type': 'application/json'})


def api_put(client, path, data):
    return client.put(path, json=data,
                      headers={'X-CSRF-Token': TEST_CSRF,
                               'Content-Type': 'application/json'})

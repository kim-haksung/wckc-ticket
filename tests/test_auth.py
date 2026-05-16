"""
============================================================
  인증 API 테스트 하네스 (test_auth.py)
  - 회원가입 / 로그인 / 로그아웃
  - 비밀번호 재설정 / 아이디 중복 확인
============================================================
"""
import pytest
from tests.helpers import h, get_csrf, api_post, create_db_user, TEST_CSRF

# ── 테스트용 기본 회원 데이터 ──────────────────────────────────
BASE_USER = {
    'username': 'testmember',
    'password': 'Test1234!',
    'name':     '김하네스',
    'phone':    '010-1111-2222',
    'church':   '서울교회',
    'position': '성도',
}


# ╔═══════════════════════════════════════════════════════════╗
# ║  회원가입 하네스                                          ║
# ╚═══════════════════════════════════════════════════════════╝
class TestRegister:

    def test_register_success(self, client):
        """정상 회원가입"""
        r = client.post('/api/register', json=BASE_USER, headers=h(client))
        assert r.status_code == 200
        assert r.get_json()['ok'] is True

    def test_register_duplicate_username(self, client):
        """중복 아이디 거부"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        r = client.post('/api/register', json=BASE_USER, headers=h(client))
        assert r.status_code == 409
        assert '이미 사용' in r.get_json()['error']

    def test_register_missing_fields(self, client):
        """필수 필드 누락 거부"""
        r = client.post('/api/register',
                        json={'username': 'only_id'},
                        headers=h(client))
        assert r.status_code == 400

    def test_register_short_username(self, client):
        """아이디 4자 미만 거부"""
        user = {**BASE_USER, 'username': 'ab'}
        r = client.post('/api/register', json=user, headers=h(client))
        assert r.status_code == 400
        assert '4~20자' in r.get_json()['error']

    def test_register_short_password(self, client):
        """비밀번호 8자 미만 거부"""
        user = {**BASE_USER, 'password': '1234'}
        r = client.post('/api/register', json=user, headers=h(client))
        assert r.status_code == 400
        assert '8자' in r.get_json()['error']


# ╔═══════════════════════════════════════════════════════════╗
# ║  로그인 하네스                                            ║
# ╚═══════════════════════════════════════════════════════════╝
class TestLogin:

    def test_login_success(self, client):
        """정상 로그인"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        r = client.post('/api/login',
                        json={'username': BASE_USER['username'],
                              'password': BASE_USER['password']},
                        headers=h(client))
        data = r.get_json()
        assert r.status_code == 200
        assert data['ok'] is True
        assert data['name'] == BASE_USER['name']

    def test_login_wrong_password(self, client):
        """틀린 비밀번호 거부"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        r = client.post('/api/login',
                        json={'username': BASE_USER['username'],
                              'password': 'WrongPassword!'},
                        headers=h(client))
        assert r.status_code == 401

    def test_login_nonexistent_user(self, client):
        """존재하지 않는 아이디 거부"""
        r = client.post('/api/login',
                        json={'username': 'ghost_user',
                              'password': 'anything'},
                        headers=h(client))
        assert r.status_code == 401

    def test_login_inactive_user(self, client):
        """비활성 계정 로그인 거부"""
        import app as _app
        uid = create_db_user('inactive_user')
        conn = _app.get_db()
        conn.execute("UPDATE users SET is_active=0 WHERE id=?", (uid,))
        conn.commit()
        conn.close()

        r = client.post('/api/login',
                        json={'username': 'inactive_user',
                              'password': 'Test1234!'},
                        headers=h(client))
        assert r.status_code == 401

    def test_admin_login_success(self, client):
        """관리자 로그인 및 role 확인"""
        r = client.post('/api/login',
                        json={'username': 'admin', 'password': 'Admin1234!'},
                        headers=h(client))
        data = r.get_json()
        assert r.status_code == 200
        assert data['role'] == 'admin'

    def test_me_logged_in(self, client):
        """/api/me — 로그인 상태 확인"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        client.post('/api/login',
                    json={'username': BASE_USER['username'],
                          'password': BASE_USER['password']},
                    headers=h(client))
        r = client.get('/api/me')
        data = r.get_json()
        assert data['logged_in'] is True
        assert data['username'] == BASE_USER['username']

    def test_me_not_logged_in(self, client):
        """/api/me — 비로그인 상태"""
        r = client.get('/api/me')
        assert r.get_json()['logged_in'] is False

    def test_logout(self, client):
        """로그아웃 후 세션 삭제 확인"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        client.post('/api/login',
                    json={'username': BASE_USER['username'],
                          'password': BASE_USER['password']},
                    headers=h(client))
        r = client.post('/api/logout', headers=h(client))
        assert r.get_json()['ok'] is True
        assert client.get('/api/me').get_json()['logged_in'] is False


# ╔═══════════════════════════════════════════════════════════╗
# ║  아이디 중복 확인 하네스                                  ║
# ╚═══════════════════════════════════════════════════════════╝
class TestCheckUsername:

    def test_username_available(self, client):
        """사용 가능한 아이디"""
        r = client.get('/api/check-username?username=brandnewuser')
        assert r.get_json()['available'] is True

    def test_username_taken(self, client):
        """이미 사용 중인 아이디"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        r = client.get(
            f'/api/check-username?username={BASE_USER["username"]}')
        assert r.get_json()['available'] is False


# ╔═══════════════════════════════════════════════════════════╗
# ║  비밀번호 재설정 하네스                                   ║
# ╚═══════════════════════════════════════════════════════════╝
class TestPasswordReset:

    def test_verify_user_success(self, client):
        """본인 확인 성공 — h(client)로 실제 세션 CSRF 토큰 발급"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        r = client.post('/api/verify-user', json={
            'username': BASE_USER['username'],
            'name':     BASE_USER['name'],
            'phone':    BASE_USER['phone'],
            'church':   BASE_USER['church'],
        }, headers=h(client))
        assert r.status_code == 200
        assert r.get_json()['ok'] is True

    def test_verify_user_wrong_info(self, client):
        """본인 확인 실패 (정보 불일치)"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        r = client.post('/api/verify-user', json={
            'username': BASE_USER['username'],
            'name':     '다른이름',
            'phone':    BASE_USER['phone'],
            'church':   BASE_USER['church'],
        }, headers=h(client))
        assert r.status_code == 404

    def test_reset_password_success(self, client):
        """비밀번호 재설정 후 새 비밀번호로 로그인 가능"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        new_pw = 'NewPass9999!'
        r = client.post('/api/reset-password', json={
            'username':     BASE_USER['username'],
            'name':         BASE_USER['name'],
            'phone':        BASE_USER['phone'],
            'church':       BASE_USER['church'],
            'new_password': new_pw,
        }, headers=h(client))
        assert r.status_code == 200
        r2 = client.post('/api/login',
                         json={'username': BASE_USER['username'],
                               'password': new_pw},
                         headers={'Content-Type': 'application/json'})
        assert r2.status_code == 200

    def test_reset_password_too_short(self, client):
        """8자 미만 새 비밀번호 거부"""
        client.post('/api/register', json=BASE_USER, headers=h(client))
        r = client.post('/api/reset-password', json={
            'username':     BASE_USER['username'],
            'name':         BASE_USER['name'],
            'phone':        BASE_USER['phone'],
            'church':       BASE_USER['church'],
            'new_password': '1234',
        }, headers=h(client))
        assert r.status_code == 400


# ╔═══════════════════════════════════════════════════════════╗
# ║  CSRF 보호 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestCSRFProtection:
    """
    /api/login, /api/register 는 의도적으로 CSRF 보호 없음
    (로그인 전 세션 없어서 토큰 발급 불가 → chicken-and-egg 문제)
    CSRF 보호 테스트는 auth_client로 세션이 있는 상태에서 수행
    """

    def test_csrf_protected_endpoint_without_token_rejected(self, auth_client):
        """CSRF 보호 엔드포인트 — 토큰 없으면 403"""
        r = auth_client.post('/api/queue/heartbeat',
                             json={'token': auth_client._queue_token},
                             headers={'Content-Type': 'application/json'})
        assert r.status_code == 403
        assert 'CSRF' in r.get_json()['error']

    def test_csrf_protected_endpoint_wrong_token_rejected(self, auth_client):
        """CSRF 보호 엔드포인트 — 잘못된 토큰이면 403"""
        r = auth_client.post('/api/queue/heartbeat',
                             json={'token': auth_client._queue_token},
                             headers={'X-CSRF-Token': 'wrong-token',
                                      'Content-Type': 'application/json'})
        assert r.status_code == 403

    def test_csrf_correct_token_accepted(self, auth_client):
        """올바른 CSRF 토큰은 통과"""
        r = auth_client.post('/api/queue/heartbeat',
                             json={'token': auth_client._queue_token},
                             headers={'X-CSRF-Token': TEST_CSRF,
                                      'Content-Type': 'application/json'})
        assert r.status_code == 200

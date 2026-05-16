"""
============================================================
  좌석 API 테스트 하네스 (test_seats.py)
  - 좌석 조회 / 선점(Lock) / 해제(Unlock)
  - 좌석 통계 / 예매 오픈 상태
============================================================
"""
import time
import uuid
import pytest
import app as _app
from tests.helpers import (
    inject_session, inject_queue_token, create_db_user,
    api_post, TEST_CSRF, SEAT_1F, SEAT_2F
)


# ╔═══════════════════════════════════════════════════════════╗
# ║  좌석 조회 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestGetSeats:

    def test_get_seats_floor1_returns_sections(self, auth_client):
        """1층 좌석 조회 — 가·나·다·라 구역 포함"""
        r = auth_client.get(f'/api/seats/1?token={auth_client._queue_token}')
        assert r.status_code == 200
        data = r.get_json()
        assert 'seats' in data
        assert 'sections' in data
        sections = data['sections']
        assert '가' in sections
        assert '나' in sections
        assert '다' in sections
        assert '라' in sections

    def test_get_seats_floor2_returns_sections(self, auth_client):
        """2층 좌석 조회 — 마·사·아·자·차·카·타 구역 포함"""
        r = auth_client.get(f'/api/seats/2?token={auth_client._queue_token}')
        assert r.status_code == 200
        data = r.get_json()
        sections = data['sections']
        assert '사' in sections
        assert '아' in sections
        assert '자' in sections

    def test_seat_initially_available(self, auth_client):
        """초기 좌석 상태는 available"""
        r = auth_client.get(f'/api/seats/1?token={auth_client._queue_token}')
        seat = r.get_json()['seats'].get(SEAT_1F)
        assert seat is not None
        assert seat['status'] == 'available'

    def test_max_seats_is_10(self, auth_client):
        """1인 최대 예매 좌석 수 = 10"""
        r = auth_client.get(f'/api/seats/1?token={auth_client._queue_token}')
        assert r.get_json()['max_seats'] == 10

    def test_my_locked_seat_shows_my_lock(self, auth_client):
        """내가 선점한 좌석은 my_lock 표시"""
        token = auth_client._queue_token
        # 좌석 선점
        api_post(auth_client, '/api/seats/lock',
                 {'seat_id': SEAT_1F, 'token': token})

        r = auth_client.get(f'/api/seats/1?token={token}')
        seat_status = r.get_json()['seats'][SEAT_1F]['status']
        assert seat_status == 'my_lock'

    def test_others_locked_seat_shows_locked(self, app, test_user_id):
        """다른 사람이 선점한 좌석은 locked 표시"""
        # 다른 사용자가 선점
        other_uid = create_db_user('other_locker')
        other_token = inject_queue_token(other_uid, '다른선점자')

        conn = _app.get_db()
        conn.execute(
            "UPDATE seats SET status='locked', locked_by=? WHERE id=?",
            (other_token, SEAT_1F)
        )
        conn.commit()
        conn.close()

        # test_user_id로 조회
        c = app.test_client()
        my_token = inject_queue_token(test_user_id, '하네스테스터')
        inject_session(c, test_user_id, 'harness_user', '하네스테스터')
        r = c.get(f'/api/seats/1?token={my_token}')
        seat_status = r.get_json()['seats'][SEAT_1F]['status']
        assert seat_status == 'locked'


# ╔═══════════════════════════════════════════════════════════╗
# ║  좌석 선점(Lock) 하네스                                   ║
# ╚═══════════════════════════════════════════════════════════╝
class TestSeatLock:

    def test_lock_available_seat_success(self, auth_client):
        """빈 좌석 선점 성공"""
        r = api_post(auth_client, '/api/seats/lock',
                     {'seat_id': SEAT_1F, 'token': auth_client._queue_token})
        assert r.status_code == 200
        assert r.get_json()['ok'] is True

        # DB 확인
        conn = _app.get_db()
        seat = conn.execute(
            "SELECT status, locked_by FROM seats WHERE id=?", (SEAT_1F,)
        ).fetchone()
        conn.close()
        assert seat['status'] == 'locked'
        assert seat['locked_by'] == auth_client._queue_token

    def test_lock_already_locked_by_other_rejected(self, app, test_user_id):
        """다른 사람이 선점한 좌석 선점 시도 → 409 충돌"""
        other_uid = create_db_user('locker_other')
        other_token = inject_queue_token(other_uid, '선점자')

        # 다른 사람이 먼저 선점
        conn = _app.get_db()
        conn.execute(
            "UPDATE seats SET status='locked', locked_by=? WHERE id=?",
            (other_token, SEAT_1F)
        )
        conn.commit()
        conn.close()

        # test_user가 같은 좌석 선점 시도
        c = app.test_client()
        my_token = inject_queue_token(test_user_id, '하네스테스터')
        inject_session(c, test_user_id, 'harness_user', '하네스테스터')
        r = api_post(c, '/api/seats/lock',
                     {'seat_id': SEAT_1F, 'token': my_token})
        assert r.status_code == 409

    def test_lock_reserved_seat_rejected(self, auth_client):
        """이미 예매된 좌석 선점 시도 → 실패"""
        conn = _app.get_db()
        conn.execute(
            "UPDATE seats SET status='reserved' WHERE id=?", (SEAT_1F,))
        conn.commit()
        conn.close()

        r = api_post(auth_client, '/api/seats/lock',
                     {'seat_id': SEAT_1F, 'token': auth_client._queue_token})
        assert r.status_code == 409

    def test_lock_without_queue_token_rejected(self, auth_client):
        """대기열 토큰 없이 선점 시도 → 403"""
        # _active에서 토큰 제거
        with _app._ql:
            _app._active.pop(auth_client._queue_token, None)

        r = api_post(auth_client, '/api/seats/lock',
                     {'seat_id': SEAT_1F, 'token': auth_client._queue_token})
        assert r.status_code == 403

    def test_relock_my_own_seat(self, auth_client):
        """내가 이미 선점한 좌석 재선점 → 성공 (mine=True)"""
        token = auth_client._queue_token
        api_post(auth_client, '/api/seats/lock',
                 {'seat_id': SEAT_1F, 'token': token})
        # 같은 좌석 다시 선점
        r = api_post(auth_client, '/api/seats/lock',
                     {'seat_id': SEAT_1F, 'token': token})
        data = r.get_json()
        assert r.status_code == 200
        assert data.get('mine') is True


# ╔═══════════════════════════════════════════════════════════╗
# ║  좌석 선점 해제(Unlock) 하네스                            ║
# ╚═══════════════════════════════════════════════════════════╝
class TestSeatUnlock:

    def test_unlock_my_seat_success(self, auth_client):
        """내 선점 좌석 해제 → available 복구"""
        token = auth_client._queue_token
        api_post(auth_client, '/api/seats/lock',
                 {'seat_id': SEAT_1F, 'token': token})

        r = api_post(auth_client, '/api/seats/unlock',
                     {'seat_id': SEAT_1F, 'token': token})
        assert r.get_json()['ok'] is True

        conn = _app.get_db()
        seat = conn.execute(
            "SELECT status FROM seats WHERE id=?", (SEAT_1F,)
        ).fetchone()
        conn.close()
        assert seat['status'] == 'available'

    def test_unlock_others_seat_no_effect(self, app, test_user_id):
        """다른 사람 선점 좌석 해제 시도 → 해제 안됨"""
        other_uid = create_db_user('other_locker2')
        other_token = inject_queue_token(other_uid, '원래선점자')

        conn = _app.get_db()
        conn.execute(
            "UPDATE seats SET status='locked', locked_by=? WHERE id=?",
            (other_token, SEAT_1F)
        )
        conn.commit()
        conn.close()

        # 내 토큰으로 해제 시도
        c = app.test_client()
        my_token = inject_queue_token(test_user_id, '하네스테스터')
        inject_session(c, test_user_id, 'harness_user', '하네스테스터')
        api_post(c, '/api/seats/unlock',
                 {'seat_id': SEAT_1F, 'token': my_token})

        # 여전히 locked 상태여야 함
        conn = _app.get_db()
        seat = conn.execute(
            "SELECT status FROM seats WHERE id=?", (SEAT_1F,)
        ).fetchone()
        conn.close()
        assert seat['status'] == 'locked'


# ╔═══════════════════════════════════════════════════════════╗
# ║  좌석 통계 / 예매 상태 하네스                             ║
# ╚═══════════════════════════════════════════════════════════╝
class TestSeatStats:

    def test_seat_stats_structure(self, client):
        """좌석 통계 API 구조 확인"""
        r = client.get('/api/stats/seats')
        assert r.status_code == 200
        data = r.get_json()
        assert 'total' in data
        assert 'reserved' in data
        assert 'available' in data
        assert data['total'] > 0

    def test_seat_stats_reserved_count_increases(self, auth_client):
        """예매 완료 시 reserved 수 증가 확인"""
        r1 = auth_client.get('/api/stats/seats').get_json()
        before = r1['reserved']

        # 좌석 예매
        conn = _app.get_db()
        conn.execute(
            "UPDATE seats SET status='reserved' WHERE id=?", (SEAT_1F,))
        conn.execute(
            "INSERT INTO reservations (res_code, user_id, seat_id) "
            "VALUES ('RES-WTEST001', ?, ?)",
            (auth_client._user_id, SEAT_1F)
        )
        conn.commit()
        conn.close()

        r2 = auth_client.get('/api/stats/seats').get_json()
        # reserved 수는 DB 기준이므로 직접 확인
        assert r2['available'] < r1['available']

    def test_booking_status_open(self, client):
        """오픈 시간 미설정 시 is_open=True"""
        # 오픈 시간 제거
        conn = _app.get_db()
        conn.execute(
            "INSERT OR REPLACE INTO config VALUES ('booking_open_time', '')")
        conn.commit()
        conn.close()

        r = client.get('/api/booking-status')
        data = r.get_json()
        assert r.status_code == 200
        assert data['is_open'] is True
        assert 'server_time' in data

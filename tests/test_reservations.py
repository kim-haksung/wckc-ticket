"""
============================================================
  예매 API 테스트 하네스 (test_reservations.py)
  - 예매 생성 / 조회 / 취소
  - 핵심: 동시 예매 충돌 방지 (Race Condition 테스트)
============================================================
"""
import threading
import time
import uuid
import pytest
import app as _app
from tests.helpers import (
    inject_session, inject_queue_token, create_db_user,
    api_post, api_delete, TEST_CSRF, SEAT_1F, SEAT_2F
)


# ── 헬퍼: 예매 전용 빠른 setup ─────────────────────────────────
def quick_book(client, seat_id, token, user_id):
    """좌석 선점 → 예매 확정 원스텝"""
    conn = _app.get_db()
    conn.execute(
        "UPDATE seats SET status='locked', locked_by=? WHERE id=?",
        (token, seat_id))
    conn.commit()
    conn.close()
    return api_post(client, '/api/reservations',
                    {'seat_ids': [seat_id], 'queue_token': token})


# ╔═══════════════════════════════════════════════════════════╗
# ║  예매 생성 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestCreateReservation:

    def test_book_locked_seat_success(self, auth_client):
        """내가 선점한 좌석 예매 성공"""
        r = quick_book(auth_client, SEAT_1F, auth_client._queue_token,
                       auth_client._queue_token)
        data = r.get_json()
        assert r.status_code == 200
        assert data['ok'] is True
        assert len(data['reservations']) == 1
        assert data['reservations'][0]['seat_id'] == SEAT_1F

        # DB 상태 확인
        conn = _app.get_db()
        seat = conn.execute(
            "SELECT status FROM seats WHERE id=?", (SEAT_1F,)).fetchone()
        res = conn.execute(
            "SELECT status FROM reservations WHERE seat_id=?",
            (SEAT_1F,)).fetchone()
        conn.close()
        assert seat['status'] == 'reserved'
        assert res['status'] == 'confirmed'

    def test_book_available_seat_success(self, auth_client):
        """선점 없이 available 좌석 바로 예매 성공"""
        r = api_post(auth_client, '/api/reservations',
                     {'seat_ids': [SEAT_1F],
                      'queue_token': auth_client._queue_token})
        assert r.status_code == 200

    def test_book_no_seats_selected(self, auth_client):
        """좌석 미선택 예매 거부"""
        r = api_post(auth_client, '/api/reservations',
                     {'seat_ids': [], 'queue_token': auth_client._queue_token})
        assert r.status_code == 400

    def test_book_already_reserved_seat(self, auth_client):
        """이미 예매된 좌석 재예매 거부 → 409"""
        # 먼저 예매
        quick_book(auth_client, SEAT_1F, auth_client._queue_token,
                   auth_client._queue_token)
        # 같은 좌석 재시도
        r = api_post(auth_client, '/api/reservations',
                     {'seat_ids': [SEAT_1F],
                      'queue_token': auth_client._queue_token})
        assert r.status_code == 409

    def test_book_others_locked_seat_rejected(self, app, test_user_id):
        """다른 사람이 선점한 좌석 예매 거부"""
        other_uid = create_db_user('other_booker')
        other_token = inject_queue_token(other_uid, '다른예매자')

        # 다른 사람이 선점
        conn = _app.get_db()
        conn.execute(
            "UPDATE seats SET status='locked', locked_by=? WHERE id=?",
            (other_token, SEAT_1F))
        conn.commit()
        conn.close()

        # test_user가 예매 시도
        c = app.test_client()
        my_token = inject_queue_token(test_user_id, '하네스테스터')
        inject_session(c, test_user_id, 'harness_user', '하네스테스터')
        r = api_post(c, '/api/reservations',
                     {'seat_ids': [SEAT_1F], 'queue_token': my_token})
        assert r.status_code == 409

    def test_book_exceeds_max_10_seats(self, auth_client):
        """10석 초과 예매 거부"""
        # 11개 좌석 ID 준비 (가001~가011)
        seat_ids = [f'가{str(i).zfill(3)}' for i in range(1, 12)]
        r = api_post(auth_client, '/api/reservations',
                     {'seat_ids': seat_ids,
                      'queue_token': auth_client._queue_token})
        assert r.status_code == 400
        assert '10석' in r.get_json()['error']

    def test_book_multiple_seats_at_once(self, auth_client):
        """여러 좌석 동시 예매 성공"""
        seat_ids = [f'가{str(i).zfill(3)}' for i in range(1, 4)]
        r = api_post(auth_client, '/api/reservations',
                     {'seat_ids': seat_ids,
                      'queue_token': auth_client._queue_token})
        data = r.get_json()
        assert r.status_code == 200
        assert len(data['reservations']) == 3

    def test_book_requires_login(self, client):
        """비로그인 상태 예매 거부"""
        r = api_post(client, '/api/reservations',
                     {'seat_ids': [SEAT_1F], 'queue_token': 'any'})
        assert r.status_code in (401, 403)


# ╔═══════════════════════════════════════════════════════════╗
# ║  예매 조회 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestMyReservations:

    def test_my_reservations_empty(self, auth_client):
        """예매 내역 없을 때 빈 리스트"""
        r = auth_client.get('/api/reservations/my')
        assert r.status_code == 200
        assert r.get_json()['reservations'] == []

    def test_my_reservations_after_booking(self, auth_client):
        """예매 후 내역 조회"""
        quick_book(auth_client, SEAT_1F, auth_client._queue_token,
                   auth_client._queue_token)
        r = auth_client.get('/api/reservations/my')
        reservations = r.get_json()['reservations']
        assert len(reservations) == 1
        assert reservations[0]['section'] == '가'
        assert reservations[0]['seat_no'] == '001'
        assert reservations[0]['status'] == 'confirmed'
        assert 'res_code' in reservations[0]


# ╔═══════════════════════════════════════════════════════════╗
# ║  예매 취소 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestCancelReservation:

    def test_cancel_own_reservation(self, auth_client):
        """본인 예매 취소 성공"""
        quick_book(auth_client, SEAT_1F, auth_client._queue_token,
                   auth_client._queue_token)
        res_id = auth_client.get('/api/reservations/my').get_json()[
            'reservations'][0]['id']

        r = api_delete(auth_client, f'/api/reservations/{res_id}')
        assert r.status_code == 200
        assert r.get_json()['ok'] is True

        # 좌석이 다시 available로 변경되지 않음 (취소는 status만 변경)
        conn = _app.get_db()
        res = conn.execute(
            "SELECT status FROM reservations WHERE id=?", (res_id,)
        ).fetchone()
        conn.close()
        assert res['status'] == 'cancelled'

    def test_cancel_already_cancelled(self, auth_client):
        """이미 취소된 예매 재취소 거부"""
        quick_book(auth_client, SEAT_1F, auth_client._queue_token,
                   auth_client._queue_token)
        res_id = auth_client.get('/api/reservations/my').get_json()[
            'reservations'][0]['id']

        api_delete(auth_client, f'/api/reservations/{res_id}')
        r = api_delete(auth_client, f'/api/reservations/{res_id}')
        assert r.status_code == 400

    def test_cancel_others_reservation_rejected(self, app, test_user_id):
        """다른 사람 예매 취소 거부 → 404"""
        # 다른 사람이 예매
        other_uid = create_db_user('cancel_other')
        conn = _app.get_db()
        conn.execute(
            "UPDATE seats SET status='reserved' WHERE id=?", (SEAT_1F,))
        conn.execute(
            "INSERT INTO reservations (res_code, user_id, seat_id) "
            "VALUES ('RES-WOTHER01', ?, ?)", (other_uid, SEAT_1F))
        conn.commit()
        res_id = conn.execute(
            "SELECT id FROM reservations WHERE res_code='RES-WOTHER01'"
        ).fetchone()['id']
        conn.close()

        # test_user가 취소 시도
        c = app.test_client()
        inject_session(c, test_user_id, 'harness_user', '하네스테스터')
        r = api_delete(c, f'/api/reservations/{res_id}')
        assert r.status_code == 404


# ╔═══════════════════════════════════════════════════════════╗
# ║  ★ 핵심 테스트: 동시 예매 충돌 방지 (Race Condition)     ║
# ╚═══════════════════════════════════════════════════════════╝
class TestConcurrentBooking:

    def test_concurrent_same_seat_only_one_wins(self, app):
        """
        [동시성 테스트] N명이 동일 좌석을 동시에 예매할 때
        반드시 1명만 성공해야 함 — BEGIN IMMEDIATE 원자성 검증
        """
        N = 30                  # 동시 예매 시도 인원
        TARGET_SEAT = '나001'   # 경합 대상 좌석

        # ── setup: N명의 사용자 생성 및 대기열 토큰 주입 ──────
        user_data = []
        for i in range(N):
            uid = create_db_user(f'concurrent_{i}', name=f'동시예매자{i}')
            user_data.append(uid)

        results = []
        errors  = []
        lock    = threading.Lock()

        # ── 스레드 함수: 각 사용자가 독립된 클라이언트로 예매 시도 ──
        def try_book(uid, idx):
            try:
                c = app.test_client()
                token = inject_queue_token(uid, f'동시예매자{idx}')
                inject_session(c, uid, f'concurrent_{idx}',
                               f'동시예매자{idx}')
                resp = c.post('/api/reservations',
                              json={'seat_ids': [TARGET_SEAT],
                                    'queue_token': token},
                              headers={'X-CSRF-Token': TEST_CSRF,
                                       'Content-Type': 'application/json'})
                with lock:
                    results.append(resp.status_code)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        # ── N개 스레드 동시 시작 ──────────────────────────────
        barrier = threading.Barrier(N)          # 모든 스레드가 준비될 때까지 대기

        def try_book_synced(uid, idx):
            barrier.wait()                      # 동시에 출발
            try_book(uid, idx)

        threads = [
            threading.Thread(target=try_book_synced, args=(uid, i))
            for i, uid in enumerate(user_data)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # ── 검증 ──────────────────────────────────────────────
        assert len(errors) == 0, f"스레드 오류 발생: {errors}"
        success_count = results.count(200)
        assert success_count == 1, (
            f"[FAIL] 동시 예매 성공 건수 = {success_count} (기대값: 1)\n"
            f"결과 분포: {dict((c, results.count(c)) for c in set(results))}"
        )

        # DB 최종 상태 확인
        conn = _app.get_db()
        confirmed = conn.execute(
            "SELECT COUNT(*) FROM reservations "
            "WHERE seat_id=? AND status='confirmed'",
            (TARGET_SEAT,)
        ).fetchone()[0]
        conn.close()
        assert confirmed == 1, f"DB 확정 예매 수 = {confirmed} (기대값: 1)"

    def test_concurrent_different_seats_all_succeed(self, app):
        """
        [동시성 테스트] N명이 각자 다른 좌석을 예매할 때
        모두 성공해야 함 — 좌석 간 충돌 없음 검증
        """
        N = 10
        seat_ids = [f'다{str(i+1).zfill(3)}' for i in range(N)]

        results = []
        lock = threading.Lock()

        def try_book(uid, idx, seat_id):
            c = app.test_client()
            token = inject_queue_token(uid, f'각자예매{idx}')
            inject_session(c, uid, f'diff_seat_{idx}', f'각자예매{idx}')
            resp = c.post('/api/reservations',
                          json={'seat_ids': [seat_id],
                                'queue_token': token},
                          headers={'X-CSRF-Token': TEST_CSRF,
                                   'Content-Type': 'application/json'})
            with lock:
                results.append(resp.status_code)

        user_ids = [
            create_db_user(f'diff_seat_{i}', name=f'각자예매{i}')
            for i in range(N)
        ]

        threads = [
            threading.Thread(target=try_book, args=(uid, i, seat_ids[i]))
            for i, uid in enumerate(user_ids)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        success_count = results.count(200)
        assert success_count == N, (
            f"각자 다른 좌석 예매 — 성공 수: {success_count} / {N}"
        )

    def test_seat_lock_atomic_update(self, app):
        """
        [원자성 테스트] 동일 좌석 선점(Lock) 동시 시도
        → DB UPDATE 원자성으로 1명만 성공해야 함
        """
        TARGET = '라001'
        N = 20
        lock_results = []
        results_lock = threading.Lock()

        def try_lock(uid, idx):
            c = app.test_client()
            token = inject_queue_token(uid, f'선점자{idx}')
            inject_session(c, uid, f'lock_user_{idx}', f'선점자{idx}')
            resp = c.post('/api/seats/lock',
                          json={'seat_id': TARGET, 'token': token},
                          headers={'X-CSRF-Token': TEST_CSRF,
                                   'Content-Type': 'application/json'})
            with results_lock:
                lock_results.append(resp.status_code)

        user_ids = [
            create_db_user(f'lock_user_{i}', name=f'선점자{i}')
            for i in range(N)
        ]

        barrier = threading.Barrier(N)

        def synced_try_lock(uid, idx):
            barrier.wait()
            try_lock(uid, idx)

        threads = [
            threading.Thread(target=synced_try_lock, args=(uid, i))
            for i, uid in enumerate(user_ids)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        success = lock_results.count(200)
        assert success == 1, f"선점 성공: {success}/1, 결과분포: { {c: lock_results.count(c) for c in set(lock_results)} }"

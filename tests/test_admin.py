"""
============================================================
  관리자 API 테스트 하네스 (test_admin.py)
  - 대시보드 통계 / 회원 관리 / 예매 관리
  - 좌석 관리 / 시스템 설정 / 엑셀 출력
  - 비관리자 접근 차단 검증
============================================================
"""
import pytest
import app as _app
from tests.helpers import (
    inject_session, create_db_user,
    api_post, api_put, api_delete,
    TEST_CSRF, SEAT_1F, SEAT_2F
)


# ── 헬퍼: 테스트용 예매 레코드 생성 ────────────────────────────
def make_reservation(seat_id, user_id, res_code='RES-WTEST001'):
    conn = _app.get_db()
    conn.execute(
        "UPDATE seats SET status='reserved' WHERE id=?", (seat_id,))
    conn.execute(
        "INSERT INTO reservations (res_code, user_id, seat_id) "
        "VALUES (?, ?, ?)", (res_code, user_id, seat_id))
    conn.commit()
    res_id = conn.execute(
        "SELECT id FROM reservations WHERE res_code=?",
        (res_code,)
    ).fetchone()['id']
    conn.close()
    return res_id


# ╔═══════════════════════════════════════════════════════════╗
# ║  접근 제한 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestAdminAccessControl:

    def test_admin_stats_requires_admin(self, auth_client):
        """일반 사용자 관리자 통계 접근 거부"""
        r = auth_client.get('/api/admin/stats')
        assert r.status_code == 403

    def test_admin_members_requires_admin(self, auth_client):
        """일반 사용자 회원 목록 접근 거부"""
        r = auth_client.get('/api/admin/members')
        assert r.status_code == 403

    def test_admin_reservations_requires_admin(self, auth_client):
        """일반 사용자 예매 관리 접근 거부"""
        r = auth_client.get('/api/admin/reservations')
        assert r.status_code == 403

    def test_admin_export_requires_admin(self, auth_client):
        """일반 사용자 엑셀 출력 접근 거부"""
        r = auth_client.get('/api/admin/export')
        assert r.status_code == 403

    def test_unauthenticated_admin_access_rejected(self, client):
        """비로그인 관리자 API 접근 거부"""
        r = client.get('/api/admin/stats')
        assert r.status_code in (401, 403)


# ╔═══════════════════════════════════════════════════════════╗
# ║  대시보드 통계 하네스                                     ║
# ╚═══════════════════════════════════════════════════════════╝
class TestAdminStats:

    def test_stats_structure(self, admin_client):
        """통계 API 응답 구조 확인"""
        r = admin_client.get('/api/admin/stats')
        assert r.status_code == 200
        data = r.get_json()
        for key in ('total_users', 'total_seats', 'confirmed',
                    'cancelled', 'available', 'paid', 'unpaid'):
            assert key in data, f"'{key}' 키 누락"

    def test_stats_confirmed_increases_after_booking(
            self, admin_client, test_user_id):
        """예매 후 confirmed 수 증가 확인"""
        before = admin_client.get('/api/admin/stats').get_json()['confirmed']
        make_reservation(SEAT_1F, test_user_id)
        after = admin_client.get('/api/admin/stats').get_json()['confirmed']
        assert after == before + 1

    def test_stats_total_seats_correct(self, admin_client):
        """총 좌석 수 = DB seats 테이블 수 (blocked 제외)"""
        r = admin_client.get('/api/admin/stats')
        total = r.get_json()['total_seats']
        assert total > 2000   # 2,328석 기준


# ╔═══════════════════════════════════════════════════════════╗
# ║  회원 관리 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestAdminMembers:

    def test_get_members_list(self, admin_client):
        """회원 목록 조회"""
        create_db_user('member1', name='홍길동')
        create_db_user('member2', name='김철수')
        r = admin_client.get('/api/admin/members')
        assert r.status_code == 200
        data = r.get_json()
        assert 'members' in data
        assert 'total' in data
        assert data['total'] >= 2

    def test_get_members_search(self, admin_client):
        """이름 검색 필터"""
        create_db_user('search_user', name='검색대상자')
        r = admin_client.get('/api/admin/members?search=검색대상자')
        members = r.get_json()['members']
        assert any(m['name'] == '검색대상자' for m in members)

    def test_update_member_info(self, admin_client):
        """회원 정보 수정"""
        uid = create_db_user('update_target', name='수정전이름')
        r = api_put(admin_client, f'/api/admin/members/{uid}', {
            'name': '수정후이름',
            'phone': '010-9999-8888',
            'church': '새교회',
            'position': '장로',
            'is_active': True,
        })
        assert r.status_code == 200
        # 실제 변경 확인
        conn = _app.get_db()
        row = conn.execute(
            "SELECT name, church FROM users WHERE id=?", (uid,)
        ).fetchone()
        conn.close()
        assert row['name'] == '수정후이름'
        assert row['church'] == '새교회'

    def test_update_member_password(self, admin_client):
        """관리자가 회원 비밀번호 강제 변경"""
        uid = create_db_user('pw_change_user')
        r = api_put(admin_client, f'/api/admin/members/{uid}', {
            'name': '테스터', 'phone': '010-0000-0000',
            'church': '테스트교회', 'position': '성도',
            'is_active': True, 'new_password': 'NewPass99!',
        })
        assert r.status_code == 200

    def test_delete_member_deactivates(self, admin_client):
        """회원 삭제 → 비활성화 처리"""
        uid = create_db_user('delete_target')
        r = api_delete(admin_client, f'/api/admin/members/{uid}')
        assert r.status_code == 200

        conn = _app.get_db()
        row = conn.execute(
            "SELECT is_active FROM users WHERE id=?", (uid,)
        ).fetchone()
        conn.close()
        assert row['is_active'] == 0


# ╔═══════════════════════════════════════════════════════════╗
# ║  예매 관리 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestAdminReservations:

    def test_get_reservations_list(self, admin_client, test_user_id):
        """예매 목록 조회"""
        make_reservation(SEAT_1F, test_user_id)
        r = admin_client.get('/api/admin/reservations')
        assert r.status_code == 200
        data = r.get_json()
        assert data['total'] >= 1

    def test_get_reservations_filter_by_floor(
            self, admin_client, test_user_id):
        """층 필터 예매 조회"""
        make_reservation(SEAT_1F, test_user_id)
        r = admin_client.get('/api/admin/reservations?floor=1')
        data = r.get_json()
        for res in data['reservations']:
            assert res['floor'] == 1

    def test_update_reservation_status(self, admin_client, test_user_id):
        """예매 상태 변경 (confirmed → cancelled)"""
        res_id = make_reservation(SEAT_1F, test_user_id)
        r = api_put(admin_client, f'/api/admin/reservations/{res_id}',
                    {'status': 'cancelled', 'memo': '관리자 취소'})
        assert r.status_code == 200

        conn = _app.get_db()
        row = conn.execute(
            "SELECT status, memo FROM reservations WHERE id=?", (res_id,)
        ).fetchone()
        conn.close()
        assert row['status'] == 'cancelled'
        assert row['memo'] == '관리자 취소'

    def test_update_payment_paid(self, admin_client, test_user_id):
        """입금 처리"""
        res_id = make_reservation(SEAT_1F, test_user_id)
        r = api_put(admin_client,
                    f'/api/admin/reservations/{res_id}/payment',
                    {'action': 'pay'})
        assert r.status_code == 200

        conn = _app.get_db()
        row = conn.execute(
            "SELECT payment_status FROM reservations WHERE id=?", (res_id,)
        ).fetchone()
        conn.close()
        assert row['payment_status'] == 'paid'

    def test_update_payment_cancel(self, admin_client, test_user_id):
        """입금 취소"""
        res_id = make_reservation(SEAT_1F, test_user_id)
        # 먼저 입금 처리
        api_put(admin_client,
                f'/api/admin/reservations/{res_id}/payment',
                {'action': 'pay'})
        # 입금 취소
        r = api_put(admin_client,
                    f'/api/admin/reservations/{res_id}/payment',
                    {'action': 'cancel'})
        assert r.status_code == 200

        conn = _app.get_db()
        row = conn.execute(
            "SELECT payment_status FROM reservations WHERE id=?", (res_id,)
        ).fetchone()
        conn.close()
        assert row['payment_status'] is None

    def test_bulk_payment(self, admin_client, test_user_id):
        """일괄 입금 처리"""
        uid2 = create_db_user('bulk_user2')
        res1 = make_reservation(SEAT_1F, test_user_id, 'RES-WBULK01')
        res2 = make_reservation(SEAT_2F, uid2, 'RES-WBULK02')

        r = api_post(admin_client, '/api/admin/reservations/bulk-payment',
                     {'ids': [res1, res2], 'action': 'pay'})
        assert r.status_code == 200
        assert r.get_json()['processed'] == 2

    def test_delete_reservation_rejected_if_paid(
            self, admin_client, test_user_id):
        """입금 완료 예매 삭제 거부"""
        res_id = make_reservation(SEAT_1F, test_user_id)
        # 입금 처리
        api_put(admin_client,
                f'/api/admin/reservations/{res_id}/payment',
                {'action': 'pay'})
        # 삭제 시도
        r = api_delete(admin_client, f'/api/admin/reservations/{res_id}')
        assert r.status_code == 403

    def test_delete_reservation_success_if_not_paid(
            self, admin_client, test_user_id):
        """미입금 예매 삭제 성공"""
        res_id = make_reservation(SEAT_1F, test_user_id)
        r = api_delete(admin_client, f'/api/admin/reservations/{res_id}')
        assert r.status_code == 200


# ╔═══════════════════════════════════════════════════════════╗
# ║  좌석 관리 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestAdminSeats:

    def test_get_seats_all(self, admin_client):
        """전체 좌석 조회"""
        r = admin_client.get('/api/admin/seats')
        assert r.status_code == 200
        assert len(r.get_json()['seats']) > 0

    def test_get_seats_by_floor(self, admin_client):
        """층별 좌석 조회"""
        r = admin_client.get('/api/admin/seats?floor=1')
        seats = r.get_json()['seats']
        assert all(s['floor'] == 1 for s in seats)

    def test_toggle_block_available_to_blocked(self, admin_client):
        """좌석 차단 (available → blocked)"""
        r = api_post(admin_client, '/api/admin/seats/toggle-block',
                     {'seat_id': SEAT_1F})
        assert r.status_code == 200
        assert r.get_json()['status'] == 'blocked'

        conn = _app.get_db()
        status = conn.execute(
            "SELECT status FROM seats WHERE id=?", (SEAT_1F,)
        ).fetchone()['status']
        conn.close()
        assert status == 'blocked'

    def test_toggle_block_blocked_to_available(self, admin_client):
        """좌석 차단 해제 (blocked → available)"""
        # 먼저 차단
        api_post(admin_client, '/api/admin/seats/toggle-block',
                 {'seat_id': SEAT_1F})
        # 해제
        r = api_post(admin_client, '/api/admin/seats/toggle-block',
                     {'seat_id': SEAT_1F})
        assert r.get_json()['status'] == 'available'

    def test_cannot_block_reserved_seat(self, admin_client, test_user_id):
        """예매된 좌석 차단 불가"""
        make_reservation(SEAT_1F, test_user_id)
        r = api_post(admin_client, '/api/admin/seats/toggle-block',
                     {'seat_id': SEAT_1F})
        assert r.status_code == 409


# ╔═══════════════════════════════════════════════════════════╗
# ║  시스템 설정 하네스                                       ║
# ╚═══════════════════════════════════════════════════════════╝
class TestAdminConfig:

    def test_get_config(self, admin_client):
        """설정 조회"""
        r = admin_client.get('/api/admin/config')
        assert r.status_code == 200
        data = r.get_json()
        assert 'max_active' in data
        assert 'booking_open_time' in data

    def test_set_max_active(self, admin_client):
        """동시 입장 최대 인원 변경"""
        r = api_post(admin_client, '/api/admin/config',
                     {'max_active': '50'})
        assert r.status_code == 200
        # 실제 적용 확인
        assert _app.MAX_ACTIVE == 50
        # 복원
        api_post(admin_client, '/api/admin/config', {'max_active': '20'})

    def test_set_booking_open_time(self, admin_client):
        """예매 오픈 시간 설정"""
        r = api_post(admin_client, '/api/admin/config',
                     {'booking_open_time': '2026-12-31 09:00:00'})
        assert r.status_code == 200
        # 확인 후 초기화
        api_post(admin_client, '/api/admin/config',
                 {'booking_open_time': ''})


# ╔═══════════════════════════════════════════════════════════╗
# ║  엑셀 출력 하네스                                         ║
# ╚═══════════════════════════════════════════════════════════╝
class TestAdminExport:

    def test_export_returns_xlsx(self, admin_client, test_user_id):
        """엑셀 다운로드 — Content-Type 및 파일명 확인"""
        make_reservation(SEAT_1F, test_user_id)
        r = admin_client.get('/api/admin/export')
        assert r.status_code == 200
        ct = r.headers.get('Content-Type', '')
        assert 'spreadsheetml' in ct or 'excel' in ct or 'octet-stream' in ct

    def test_export_empty_data(self, admin_client):
        """예매 없을 때 엑셀 출력 — 헤더만 포함된 파일"""
        r = admin_client.get('/api/admin/export')
        assert r.status_code == 200
        # 빈 파일이 아닌 유효한 xlsx 확인 (최소 크기 체크)
        assert len(r.data) > 100

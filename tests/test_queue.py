"""
============================================================
  대기열 API 테스트 하네스 (test_queue.py)
  - 대기열 참가 / 상태 조회 / 하트비트 / 퇴장
  - 예매 오픈 시간 제한 / 공개 현황 API
============================================================
"""
import time
import uuid
import pytest
import app as _app
from tests.helpers import (
    inject_session, inject_queue_token, create_db_user,
    get_csrf, TEST_CSRF, api_post
)


# ── 헬퍼: 로그인된 클라이언트 + CSRF ───────────────────────────
def make_auth_client(app, username="q_user"):
    """로그인 세션이 주입된 클라이언트 반환"""
    uid = create_db_user(username, name="대기열테스터")
    c = app.test_client().__enter__()
    inject_session(c, uid, username, "대기열테스터")
    return c, uid


# ╔═══════════════════════════════════════════════════════════╗
# ║  대기열 참가 하네스                                       ║
# ╚═══════════════════════════════════════════════════════════╝
class TestQueueJoin:

    def test_join_active_immediately(self, auth_client):
        """빈 슬롯 있을 때 즉시 입장 (status=active)"""
        with _app._ql:
            _app._active.clear()

        r = auth_client.post("/api/queue/join", json={},
                             headers={"X-CSRF-Token": TEST_CSRF,
                                      "Content-Type": "application/json"})
        data = r.get_json()
        assert r.status_code == 200
        assert data["status"] == "active"
        assert "token" in data
        assert data["remaining"] > 0

    def test_join_waiting_when_full(self, app, test_user_id):
        """슬롯이 꽉 찼을 때 대기 (status=waiting)"""
        with _app._ql:
            for i in range(_app.MAX_ACTIVE):
                _app._active[f"dummy-{i}"] = {
                    "uid": 9999 + i, "name": f"더미{i}",
                    "entered_at": time.time(), "heartbeat": time.time()
                }

        c = app.test_client()
        inject_session(c, test_user_id, "harness_user", "하네스테스터")
        r = c.post("/api/queue/join", json={},
                   headers={"X-CSRF-Token": get_csrf(c),
                            "Content-Type": "application/json"})
        data = r.get_json()
        assert r.status_code == 200
        assert data["status"] == "waiting"
        assert data["position"] >= 1

    def test_join_restore_active_token(self, auth_client):
        """기존 active 토큰으로 재접속 시 복원"""
        existing_token = auth_client._queue_token
        r = auth_client.post("/api/queue/join",
                             json={"token": existing_token},
                             headers={"X-CSRF-Token": TEST_CSRF,
                                      "Content-Type": "application/json"})
        data = r.get_json()
        assert r.status_code == 200
        assert data["status"] == "active"
        assert data["token"] == existing_token

    def test_join_requires_login(self, client):
        """비로그인 상태 대기열 참가 거부"""
        r = client.post("/api/queue/join", json={},
                        headers={"X-CSRF-Token": get_csrf(client),
                                 "Content-Type": "application/json"})
        assert r.status_code == 401

    def test_join_blocked_before_open_time(self, app, test_user_id):
        """예매 오픈 전 대기열 참가 거부"""
        # 앱은 KST(UTC+9) 기준으로 비교 → 미래 시간도 KST 기준으로 설정
        import datetime
        KST = datetime.timezone(datetime.timedelta(hours=9))
        future = (datetime.datetime.now(KST).replace(tzinfo=None) +
                  datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn = _app.get_db()
        conn.execute(
            "INSERT OR REPLACE INTO config VALUES (?, ?)",
            ("booking_open_time", future))
        conn.commit()
        conn.close()
        _app._invalidate_config_cache("booking_open_time")  # Perf-① 캐시 즉시 무효화

        c = app.test_client()
        inject_session(c, test_user_id, "harness_user", "하네스테스터")
        r = c.post("/api/queue/join", json={},
                   headers={"X-CSRF-Token": get_csrf(c),
                            "Content-Type": "application/json"})
        assert r.status_code == 403
        assert "open_time" in r.get_json()

        # 정리
        conn = _app.get_db()
        conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?)",
                     ("booking_open_time", ""))
        conn.commit()
        conn.close()
        _app._invalidate_config_cache("booking_open_time")  # 정리 후에도 캐시 무효화

    def test_admin_bypasses_open_time(self, admin_client):
        """관리자는 오픈 전에도 대기열 참가 가능"""
        import datetime
        KST = datetime.timezone(datetime.timedelta(hours=9))
        future = (datetime.datetime.now(KST).replace(tzinfo=None) +
                  datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn = _app.get_db()
        conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?)",
                     ("booking_open_time", future))
        conn.commit()
        conn.close()

        r = admin_client.post("/api/queue/join", json={},
                              headers={"X-CSRF-Token": TEST_CSRF,
                                       "Content-Type": "application/json"})
        assert r.status_code == 200
        assert r.get_json()["status"] in ("active", "waiting")

        # 정리
        conn = _app.get_db()
        conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?)",
                     ("booking_open_time", ""))
        conn.commit()
        conn.close()


# ╔═══════════════════════════════════════════════════════════╗
# ║  대기열 상태 조회 하네스                                  ║
# ╚═══════════════════════════════════════════════════════════╝
class TestQueueStatus:

    def test_status_active(self, auth_client):
        """active 토큰 상태 조회"""
        token = auth_client._queue_token
        r = auth_client.get(f"/api/queue/status?token={token}")
        data = r.get_json()
        assert r.status_code == 200
        assert data["status"] == "active"
        assert "remaining" in data

    def test_status_expired_token(self, auth_client):
        """만료된(존재하지 않는) 토큰 상태 조회"""
        r = auth_client.get("/api/queue/status?token=unknown-token-xyz")
        assert r.get_json()["status"] == "expired"

    def test_status_waiting(self, app, test_user_id):
        """대기 상태 조회"""
        with _app._ql:
            for i in range(_app.MAX_ACTIVE):
                _app._active[f"full-{i}"] = {
                    "uid": 8888 + i, "name": f"꽉{i}",
                    "entered_at": time.time(), "heartbeat": time.time()
                }
        wait_token = str(uuid.uuid4())
        with _app._ql:
            _app._waiting[wait_token] = {
                "uid": test_user_id, "name": "대기자",
                "joined_at": time.time()
            }

        c = app.test_client()
        inject_session(c, test_user_id, "harness_user", "하네스테스터")
        r = c.get(f"/api/queue/status?token={wait_token}")
        data = r.get_json()
        assert data["status"] == "waiting"
        assert data["position"] == 1


# ╔═══════════════════════════════════════════════════════════╗
# ║  하트비트 하네스                                          ║
# ╚═══════════════════════════════════════════════════════════╝
class TestQueueHeartbeat:

    def test_heartbeat_active_token(self, auth_client):
        """유효한 토큰 하트비트 갱신 성공"""
        r = api_post(auth_client, "/api/queue/heartbeat",
                     {"token": auth_client._queue_token})
        data = r.get_json()
        assert r.status_code == 200
        assert data["ok"] is True
        assert "remaining" in data

    def test_heartbeat_invalid_token(self, auth_client):
        """유효하지 않은 토큰 하트비트 실패"""
        r = api_post(auth_client, "/api/queue/heartbeat",
                     {"token": "invalid-token"})
        assert r.get_json()["ok"] is False


# ╔═══════════════════════════════════════════════════════════╗
# ║  대기열 퇴장 하네스                                       ║
# ╚═══════════════════════════════════════════════════════════╝
class TestQueueLeave:

    def test_leave_removes_from_active(self, auth_client):
        """퇴장 후 _active에서 제거 확인"""
        token = auth_client._queue_token
        assert token in _app._active

        r = auth_client.post("/api/queue/leave",
                             json={"token": token},
                             headers={"Content-Type": "application/json"})
        assert r.get_json()["ok"] is True
        assert token not in _app._active

    def test_leave_fills_slot(self, app, test_user_id):
        """퇴장 시 대기자가 자동으로 입장하는지 확인"""
        with _app._ql:
            for i in range(_app.MAX_ACTIVE - 1):
                _app._active[f"slot-{i}"] = {
                    "uid": 7777 + i, "name": f"슬롯{i}",
                    "entered_at": time.time(), "heartbeat": time.time()
                }
            main_token = str(uuid.uuid4())
            _app._active[main_token] = {
                "uid": test_user_id, "name": "메인사용자",
                "entered_at": time.time(), "heartbeat": time.time()
            }
            wait_token = str(uuid.uuid4())
            _app._waiting[wait_token] = {
                "uid": 5555, "name": "대기자",
                "joined_at": time.time()
            }

        c = app.test_client()
        inject_session(c, test_user_id, "harness_user", "하네스테스터")
        c.post("/api/queue/leave",
               json={"token": main_token},
               headers={"Content-Type": "application/json"})

        with _app._ql:
            assert wait_token in _app._active
            assert wait_token not in _app._waiting


# ╔═══════════════════════════════════════════════════════════╗
# ║  공개 대기열 현황 하네스                                  ║
# ╚═══════════════════════════════════════════════════════════╝
class TestQueueInfo:

    def test_queue_info_public(self, client):
        """로그인 없이 대기열 현황 조회 가능"""
        r = client.get("/api/queue/info")
        assert r.status_code == 200
        data = r.get_json()
        assert "active" in data
        assert "waiting" in data
        assert "max_active" in data

    def test_queue_info_counts(self, auth_client):
        """active 수가 정확히 반영되는지 확인"""
        r = auth_client.get("/api/queue/info")
        data = r.get_json()
        assert data["active"] >= 1

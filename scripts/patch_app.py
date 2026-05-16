#!/usr/bin/env python3
"""
scripts/patch_app.py
====================
app.py 대형 파일 안전 패치 스크립트.

Edit 도구는 쓰기 버퍼가 원본 파일 크기로 고정되어
파일이 커지는 패치 시 말미가 잘리는 문제가 있습니다.
이 스크립트는 Python 파일 I/O를 직접 사용합니다.

사용법:
    python3 scripts/patch_app.py           # 패치 적용 + 검증
    python3 scripts/patch_app.py --verify  # 검증만 (패치 미적용)
"""
import ast
import os
import sys

APP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app.py')


def load():
    with open(APP_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def save(content):
    with open(APP_PATH, 'w', encoding='utf-8') as f:
        f.write(content)


def verify(content, label=""):
    try:
        ast.parse(content)
        lines = content.count('\n')
        size  = len(content.encode('utf-8'))
        print(f"  [OK] {label}구문 정상 | {lines}줄 | {size:,} bytes")
        return True
    except SyntaxError as e:
        print(f"  [ERR] 구문 오류 line {e.lineno}: {e.msg}")
        return False


def patch(content, old, new, label):
    if old not in content:
        if new in content:
            print(f"  [SKIP] {label} — 이미 적용됨")
            return content
        raise ValueError(
            f"패치 대상을 찾을 수 없습니다: {label}\n"
            f"  탐색 문자열 앞 60자: {repr(old[:60])}"
        )
    result = content.replace(old, new, 1)
    print(f"  [PATCH] {label}")
    return result


# ══════════════════════════════════════════════════════════════════
# 패치 목록
# ══════════════════════════════════════════════════════════════════

def apply_all_patches(content):
    """
    모든 패치를 순서대로 적용합니다.
    멱등성 보장: 이미 적용된 패치는 SKIP.
    """

    # ────────────────────────────────────────────────────────────
    # [Bug Fix] Bug-1: cancel_reservation 좌석 복원
    # ────────────────────────────────────────────────────────────
    content = patch(
        content,
        old=(
            '    now = datetime.datetime.now().strftime(\'%Y-%m-%d %H:%M:%S\')\n'
            '    conn.execute(\n'
            '        \'UPDATE reservations SET status="cancelled", cancelled_at=? WHERE id=?\',\n'
            '        (now, res_id)\n'
            '    )\n'
            '    conn.commit()\n'
            '    conn.close()\n'
            '    return jsonify({\'ok\': True, \'message\': \'예매가 취소되었습니다.\'})'
        ),
        new=(
            '    now = datetime.datetime.now().strftime(\'%Y-%m-%d %H:%M:%S\')\n'
            '    # Bug-1 수정: 취소 시 해당 좌석을 available 로 복원 (reservations 변경과 같은 트랜잭션)\n'
            '    conn.execute(\n'
            '        "UPDATE seats SET status=\'available\', locked_by=NULL, locked_at=NULL WHERE id=?",\n'
            '        (res[\'seat_id\'],)\n'
            '    )\n'
            '    conn.execute(\n'
            '        \'UPDATE reservations SET status="cancelled", cancelled_at=? WHERE id=?\',\n'
            '        (now, res_id)\n'
            '    )\n'
            '    conn.commit()\n'
            '    conn.close()\n'
            '    return jsonify({\'ok\': True, \'message\': \'예매가 취소되었습니다.\'})'
        ),
        label="Bug-1 cancel_reservation 좌석 복원"
    )

    # ────────────────────────────────────────────────────────────
    # [Bug Fix] Bug-2: admin_update_reservation 좌석 복원
    # ────────────────────────────────────────────────────────────
    content = patch(
        content,
        old=(
            '    new_status = d.get(\'status\', \'confirmed\')\n'
            '    cancelled_at = now if new_status != \'confirmed\' else None\n'
            '    conn.execute(\'UPDATE reservations SET status=?, cancelled_at=?, memo=? WHERE id=?\',\n'
            '                 (new_status, cancelled_at, d.get(\'memo\',\'\'), res_id))\n'
            '    conn.commit()\n'
            '    conn.close()\n'
            '    return jsonify({\'ok\': True})\n'
            '\n'
            '@app.route(\'/api/admin/reservations/<int:res_id>/payment\', methods=[\'PUT\'])'
        ),
        new=(
            '    new_status = d.get(\'status\', \'confirmed\')\n'
            '    cancelled_at = now if new_status != \'confirmed\' else None\n'
            '\n'
            '    # Bug-2 수정: 취소 계열 상태로 변경 시 해당 좌석을 available 로 복원\n'
            '    if new_status != \'confirmed\':\n'
            '        res_row = conn.execute(\n'
            '            \'SELECT seat_id FROM reservations WHERE id=? AND status="confirmed"\', (res_id,)\n'
            '        ).fetchone()\n'
            '        if res_row:\n'
            '            conn.execute(\n'
            '                "UPDATE seats SET status=\'available\', locked_by=NULL, locked_at=NULL WHERE id=?",\n'
            '                (res_row[\'seat_id\'],)\n'
            '            )\n'
            '\n'
            '    conn.execute(\'UPDATE reservations SET status=?, cancelled_at=?, memo=? WHERE id=?\',\n'
            '                 (new_status, cancelled_at, d.get(\'memo\',\'\'), res_id))\n'
            '    conn.commit()\n'
            '    conn.close()\n'
            '    return jsonify({\'ok\': True})\n'
            '\n'
            '@app.route(\'/api/admin/reservations/<int:res_id>/payment\', methods=[\'PUT\'])'
        ),
        label="Bug-2 admin_update_reservation 좌석 복원"
    )

    # ────────────────────────────────────────────────────────────
    # [Bug Fix] Bug-3: admin_delete_member 좌석 복원
    # ────────────────────────────────────────────────────────────
    content = patch(
        content,
        old=(
            'def admin_delete_member(uid):\n'
            '    conn = get_db()\n'
            '    conn.execute(\'UPDATE reservations SET status="admin_cancelled" WHERE user_id=? AND status="confirmed"\', (uid,))\n'
            '    conn.execute(\'UPDATE users SET is_active=0 WHERE id=?\', (uid,))\n'
            '    conn.commit()\n'
            '    conn.close()\n'
            '    return jsonify({\'ok\': True})'
        ),
        new=(
            'def admin_delete_member(uid):\n'
            '    conn = get_db()\n'
            '\n'
            '    # Bug-3 수정: reservations 취소 전에 seat_id 목록을 먼저 조회 → 좌석 복원\n'
            '    confirmed_seats = conn.execute(\n'
            '        \'SELECT seat_id FROM reservations WHERE user_id=? AND status="confirmed"\', (uid,)\n'
            '    ).fetchall()\n'
            '    for seat_row in confirmed_seats:\n'
            '        conn.execute(\n'
            '            "UPDATE seats SET status=\'available\', locked_by=NULL, locked_at=NULL WHERE id=?",\n'
            '            (seat_row[\'seat_id\'],)\n'
            '        )\n'
            '\n'
            '    conn.execute(\'UPDATE reservations SET status="admin_cancelled" WHERE user_id=? AND status="confirmed"\', (uid,))\n'
            '    conn.execute(\'UPDATE users SET is_active=0 WHERE id=?\', (uid,))\n'
            '    conn.commit()\n'
            '    conn.close()\n'
            '    return jsonify({\'ok\': True})'
        ),
        label="Bug-3 admin_delete_member 좌석 복원"
    )

    # ════════════════════════════════════════════════════════════
    # [Perf-①] Config 값 인-메모리 캐싱 (TTL 5초)
    #   - 매 요청마다 DB 조회 → 5초 캐시 적용
    #   - 관리자 설정 변경 시 즉시 무효화
    # ════════════════════════════════════════════════════════════
    content = patch(
        content,
        old=(
            'def get_config_value(key, default=None):\n'
            '    """config 테이블에서 설정값 조회"""\n'
            '    try:\n'
            '        conn = get_db()\n'
            '        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()\n'
            '        conn.close()\n'
            '        return row[0] if (row and row[0] is not None and row[0] != \'\') else default\n'
            '    except Exception:\n'
            '        return default'
        ),
        new=(
            '# ── Perf-① config 인-메모리 캐시 (TTL 5초) ───────────────────\n'
            '_config_cache      = {}              # key → (value, timestamp)\n'
            '_config_cache_lock = threading.Lock()\n'
            '_CONFIG_TTL        = 5               # 초 단위\n'
            '\n'
            'def _invalidate_config_cache(key=None):\n'
            '    """관리자 설정 변경 시 캐시 즉시 무효화"""\n'
            '    with _config_cache_lock:\n'
            '        if key:\n'
            '            _config_cache.pop(key, None)\n'
            '        else:\n'
            '            _config_cache.clear()\n'
            '\n'
            'def get_config_value(key, default=None):\n'
            '    """config 테이블에서 설정값 조회 (TTL 캐시 적용)"""\n'
            '    now = time.time()\n'
            '    with _config_cache_lock:\n'
            '        if key in _config_cache:\n'
            '            val, ts = _config_cache[key]\n'
            '            if now - ts < _CONFIG_TTL:\n'
            '                return val if val is not None else default\n'
            '    try:\n'
            '        conn = get_db()\n'
            '        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()\n'
            '        conn.close()\n'
            '        val = row[0] if (row and row[0] is not None and row[0] != \'\') else None\n'
            '        with _config_cache_lock:\n'
            '            _config_cache[key] = (val, time.time())\n'
            '        return val if val is not None else default\n'
            '    except Exception:\n'
            '        return default'
        ),
        label="Perf-① get_config_value TTL 캐시"
    )

    # admin_set_config 에서 캐시 무효화 호출 추가
    content = patch(
        content,
        old=(
            '    conn.commit()\n'
            '    conn.close()\n'
            '    return jsonify({\'ok\': True})\n'
            '\n'
            '\n'
            '# ────────────────────────────────────────────────────────────\n'
            '# 앱 시작'
        ),
        new=(
            '    conn.commit()\n'
            '    conn.close()\n'
            '    _invalidate_config_cache()  # Perf-①: 설정 변경 시 캐시 즉시 무효화\n'
            '    return jsonify({\'ok\': True})\n'
            '\n'
            '\n'
            '# ────────────────────────────────────────────────────────────\n'
            '# 앱 시작'
        ),
        label="Perf-① admin_set_config 캐시 무효화 호출"
    )

    # ════════════════════════════════════════════════════════════
    # [Perf-②] _ql 보유 중 DB I/O 분리
    #   - _queue_kick: 메모리 조작만 (_ql 내부)
    #   - _release_seat_lock_db: DB 작업 (_ql 외부)
    #   - _queue_cleanup_loop / queue_leave: _ql 해제 후 DB 호출
    # ════════════════════════════════════════════════════════════
    content = patch(
        content,
        old=(
            'def _queue_kick(token):\n'
            '    """활성 세션 퇴장 + 좌석 lock 해제 + 빈 슬롯 보충 (lock 보유 상태에서 호출)"""\n'
            '    _active.pop(token, None)\n'
            '    try:\n'
            '        conn = sqlite3.connect(os.environ.get("TICKET_DB", os.path.join(\n'
            '            os.path.dirname(os.path.abspath(__file__)), "tickets.db")), timeout=10)\n'
            '        conn.execute(\'PRAGMA journal_mode = WAL\')\n'
            '        conn.execute("UPDATE seats SET status=\'available\', locked_by=NULL, locked_at=NULL "\n'
            '                     "WHERE locked_by=? AND status=\'locked\'", (token,))\n'
            '        conn.commit(); conn.close()\n'
            '    except Exception: pass\n'
            '    _queue_fill()'
        ),
        new=(
            '# Perf-②: _ql 보유 중 DB I/O 제거 → 잠금 점유 시간 최소화\n'
            'def _release_seat_lock_db(token):\n'
            '    """좌석 lock DB 해제 (_ql 외부에서 호출해야 함)"""\n'
            '    try:\n'
            '        _db = os.environ.get("TICKET_DB", os.path.join(\n'
            '            os.path.dirname(os.path.abspath(__file__)), "tickets.db"))\n'
            '        conn = sqlite3.connect(_db, timeout=10)\n'
            '        conn.execute(\'PRAGMA journal_mode = WAL\')\n'
            '        conn.execute(\n'
            '            "UPDATE seats SET status=\'available\', locked_by=NULL, locked_at=NULL "\n'
            '            "WHERE locked_by=? AND status=\'locked\'", (token,))\n'
            '        conn.commit()\n'
            '        conn.close()\n'
            '    except Exception:\n'
            '        pass\n'
            '\n'
            'def _queue_kick(token):\n'
            '    """활성 세션 메모리 퇴장 + 슬롯 보충 (_ql 보유 상태에서 호출)\n'
            '    DB 좌석 해제는 _ql 해제 후 _release_seat_lock_db(token) 로 처리.\n'
            '    """\n'
            '    _active.pop(token, None)\n'
            '    _queue_fill()'
        ),
        label="Perf-② _queue_kick DB I/O 분리 + _release_seat_lock_db 추가"
    )

    # _queue_cleanup_loop: _ql 해제 후 DB 호출
    content = patch(
        content,
        old=(
            'def _queue_cleanup_loop():\n'
            '    """백그라운드: 하트비트 만료 + 좌석 lock 만료 처리"""\n'
            '    while True:\n'
            '        time.sleep(5)\n'
            '        now = time.time()\n'
            '        with _ql:\n'
            '            # 하트비트 타임아웃\n'
            '            expired = [t for t, v in list(_active.items())\n'
            '                       if now - v[\'heartbeat\'] > HEARTBEAT_LIMIT]\n'
            '            for t in expired:\n'
            '                _queue_kick(t)\n'
            '            # 30분 초과 대기자 제거\n'
            '            old = [t for t, v in list(_waiting.items())\n'
            '                   if now - v[\'joined_at\'] > 1800]\n'
            '            for t in old:\n'
            '                _waiting.pop(t, None)\n'
            '        # DB 좌석 lock 만료 (5분 초과)'
        ),
        new=(
            'def _queue_cleanup_loop():\n'
            '    """백그라운드: 하트비트 만료 + 좌석 lock 만료 처리"""\n'
            '    while True:\n'
            '        time.sleep(5)\n'
            '        now = time.time()\n'
            '        expired_tokens = []\n'
            '        with _ql:\n'
            '            # 하트비트 타임아웃\n'
            '            expired = [t for t, v in list(_active.items())\n'
            '                       if now - v[\'heartbeat\'] > HEARTBEAT_LIMIT]\n'
            '            for t in expired:\n'
            '                _queue_kick(t)          # 메모리만 (_ql 내부)\n'
            '                expired_tokens.append(t)\n'
            '            # 30분 초과 대기자 제거\n'
            '            old = [t for t, v in list(_waiting.items())\n'
            '                   if now - v[\'joined_at\'] > 1800]\n'
            '            for t in old:\n'
            '                _waiting.pop(t, None)\n'
            '        # Perf-②: _ql 해제 후 DB 작업 (잠금 점유 최소화)\n'
            '        for t in expired_tokens:\n'
            '            _release_seat_lock_db(t)\n'
            '        # DB 좌석 lock 만료 (5분 초과)'
        ),
        label="Perf-② _queue_cleanup_loop _ql 해제 후 DB 호출"
    )

    # queue_leave: _ql 해제 후 DB 호출
    content = patch(
        content,
        old=(
            'def queue_leave():\n'
            '    """자발적 퇴장 (브라우저 종료, 뒤로가기 등)"""\n'
            '    token = (request.json or {}).get(\'token\', \'\')\n'
            '    with _ql:\n'
            '        if token in _active:\n'
            '            _queue_kick(token)\n'
            '        elif token in _waiting:\n'
            '            _waiting.pop(token, None)\n'
            '    return jsonify({\'ok\': True})'
        ),
        new=(
            'def queue_leave():\n'
            '    """자발적 퇴장 (브라우저 종료, 뒤로가기 등)"""\n'
            '    token = (request.json or {}).get(\'token\', \'\')\n'
            '    kicked = False\n'
            '    with _ql:\n'
            '        if token in _active:\n'
            '            _queue_kick(token)   # 메모리만 (_ql 내부)\n'
            '            kicked = True\n'
            '        elif token in _waiting:\n'
            '            _waiting.pop(token, None)\n'
            '    # Perf-②: _ql 해제 후 DB 작업\n'
            '    if kicked:\n'
            '        _release_seat_lock_db(token)\n'
            '    return jsonify({\'ok\': True})'
        ),
        label="Perf-② queue_leave _ql 해제 후 DB 호출"
    )

    # ════════════════════════════════════════════════════════════
    # [Perf-③] SQLite 쓰기 병목 완화
    #   A. 예매 동시 진입 세마포어 (최대 10개 동시 처리)
    #   B. BEGIN IMMEDIATE 실패 시 재시도 (최대 3회, 지수 백오프)
    # ════════════════════════════════════════════════════════════

    # 세마포어 변수 선언 (대기열 변수 선언부 바로 아래에 추가)
    content = patch(
        content,
        old=(
            '_ql      = threading.Lock()\n'
            '_active  = {}            # token → {uid, name, entered_at, heartbeat}\n'
            '_waiting = OrderedDict() # token → {uid, name, joined_at}'
        ),
        new=(
            '_ql      = threading.Lock()\n'
            '_active  = {}            # token → {uid, name, entered_at, heartbeat}\n'
            '_waiting = OrderedDict() # token → {uid, name, joined_at}\n'
            '\n'
            '# Perf-③: 동시 예매 확정 요청 제한 (SQLite BEGIN IMMEDIATE 충돌 최소화)\n'
            '_reservation_sem = threading.Semaphore(10)  # 동시 처리 최대 10개'
        ),
        label="Perf-③ 예매 세마포어 변수 선언"
    )

    # create_reservation 함수에 세마포어 + BEGIN IMMEDIATE 재시도 적용
    content = patch(
        content,
        old=(
            '    # isolation_level=None: 수동 트랜잭션 관리 (BEGIN IMMEDIATE 사용을 위해 필요)\n'
            '    conn = sqlite3.connect(DATABASE, timeout=10)\n'
            '    conn.row_factory = sqlite3.Row\n'
            '    conn.execute(\'PRAGMA foreign_keys = ON\')\n'
            '    conn.execute(\'PRAGMA journal_mode = WAL\')\n'
            '    conn.isolation_level = None  # autocommit 모드 → 명시적 트랜잭션 사용\n'
            '\n'
            '    def rollback_and_close():\n'
            '        try:\n'
            '            conn.execute(\'ROLLBACK\')\n'
            '        except Exception:\n'
            '            pass\n'
            '        conn.close()\n'
            '\n'
            '    try:\n'
            '        # BEGIN IMMEDIATE: 이 시점부터 쓰기 잠금 확보 → 동시 예매 중복 원천 차단\n'
            '        conn.execute(\'BEGIN IMMEDIATE\')'
        ),
        new=(
            '    # Perf-③A: 세마포어로 동시 처리 수 제한 (5초 대기 후 포기 → 503)\n'
            '    if not _reservation_sem.acquire(blocking=True, timeout=5):\n'
            '        return jsonify({\'error\': \'예매 요청이 많습니다. 잠시 후 다시 시도해주세요.\'}), 503\n'
            '\n'
            '    # isolation_level=None: 수동 트랜잭션 관리 (BEGIN IMMEDIATE 사용을 위해 필요)\n'
            '    conn = sqlite3.connect(DATABASE, timeout=10)\n'
            '    conn.row_factory = sqlite3.Row\n'
            '    conn.execute(\'PRAGMA foreign_keys = ON\')\n'
            '    conn.execute(\'PRAGMA journal_mode = WAL\')\n'
            '    conn.isolation_level = None  # autocommit 모드 → 명시적 트랜잭션 사용\n'
            '\n'
            '    def rollback_and_close():\n'
            '        try:\n'
            '            conn.execute(\'ROLLBACK\')\n'
            '        except Exception:\n'
            '            pass\n'
            '        conn.close()\n'
            '        _reservation_sem.release()  # Perf-③: 세마포어 반드시 해제\n'
            '\n'
            '    try:\n'
            '        # Perf-③B: BEGIN IMMEDIATE 재시도 (최대 3회, 지수 백오프 50ms→100ms)\n'
            '        # 동시 예매 충돌 시 즉시 503 대신 짧게 대기 후 재시도\n'
            '        for _attempt in range(3):\n'
            '            try:\n'
            '                conn.execute(\'BEGIN IMMEDIATE\')\n'
            '                break\n'
            '            except sqlite3.OperationalError as _e:\n'
            '                if \'locked\' in str(_e).lower() and _attempt < 2:\n'
            '                    time.sleep(0.05 * (2 ** _attempt))  # 50ms, 100ms\n'
            '                    continue\n'
            '                conn.close()\n'
            '                _reservation_sem.release()\n'
            '                return jsonify({\'error\': \'일시적으로 처리 중입니다. 잠시 후 다시 시도해주세요.\'}), 503'
        ),
        label="Perf-③ create_reservation 세마포어 + BEGIN IMMEDIATE 재시도"
    )

    # COMMIT 후 세마포어 해제 추가
    content = patch(
        content,
        old=(
            '        conn.execute(\'COMMIT\')\n'
            '        conn.close()\n'
            '        return jsonify({\'ok\': True, \'reservations\': created,\n'
            '                        \'message\': f\'{len(created)}석 예매가 완료되었습니다.\'})'
        ),
        new=(
            '        conn.execute(\'COMMIT\')\n'
            '        conn.close()\n'
            '        _reservation_sem.release()  # Perf-③: 정상 완료 후 세마포어 해제\n'
            '        return jsonify({\'ok\': True, \'reservations\': created,\n'
            '                        \'message\': f\'{len(created)}석 예매가 완료되었습니다.\'})'
        ),
        label="Perf-③ COMMIT 후 세마포어 해제"
    )

    return content


if __name__ == '__main__':
    print(f"\n대상 파일: {APP_PATH}")

    content = load()
    size_before = len(content.encode('utf-8'))
    lines_before = content.count('\n')
    print(f"읽기 완료: {lines_before}줄 | {size_before:,} bytes\n")

    if '--verify' in sys.argv:
        ok = verify(content, "현재 상태 ")
        sys.exit(0 if ok else 1)

    print("패치 적용 중...")
    try:
        patched = apply_all_patches(content)
    except ValueError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)

    print("\n검증 중...")
    if not verify(patched, "패치 후 "):
        print("[ABORT] 구문 오류로 저장 취소")
        sys.exit(1)

    save(patched)
    size_after = len(patched.encode('utf-8'))
    lines_after = patched.count('\n')
    print(
        f"\n저장 완료: {lines_after}줄 (+{lines_after - lines_before}) | "
        f"{size_after:,} bytes (+{size_after - size_before})"
    )
    print("Done.")

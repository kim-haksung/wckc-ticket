#!/usr/bin/env python3
"""
start_server.py
===============
start.bat 에서 호출되는 서버 기동 스크립트.

핵심 원칙:
  - sys.executable 로 자기 자신을 호출한 Python 을 그대로 사용
  - pip install 과 waitress 실행이 항상 동일한 인터프리터를 쓰므로
    "No module named waitress" 오류가 발생하지 않음
  - 한국어 출력을 Python 에서 처리하므로 CMD 코드페이지 문제 없음
"""
import sys
import os
import subprocess

# ── 출력 인코딩 UTF-8 강제 (Windows 터미널) ─────────────────────
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

REQUIRED = ['flask', 'openpyxl', 'waitress', 'werkzeug', 'flask-limiter']

BANNER = """
=============================================
   공연 티켓 예매 시스템 시작 (운영 서버)
=============================================
"""

INFO = """
 접속 주소 : http://127.0.0.1:5000
 관리자 ID : admin
 관리자 PW : Admin1234!
 서버 모드 : PRODUCTION (운영)
 동시처리  : 32 스레드  (300명 동시접속 최적화)
 커넥션한도 : 1000
=============================================
 서버를 종료하려면 Ctrl+C 를 누르세요.
=============================================
"""


def install_packages():
    """현재 인터프리터로 필수 패키지 설치"""
    print("[1단계] 필수 패키지 확인 중...", flush=True)
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '--quiet', '--upgrade'] + REQUIRED,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("[경고] 일부 패키지 설치 실패:", result.stderr.strip())
    else:
        print(f"  → OK  ({', '.join(REQUIRED)})")


def verify_waitress():
    """waitress 임포트 가능 여부 확인"""
    try:
        import waitress  # noqa: F401
        return True
    except ImportError:
        return False


def start_server():
    """waitress 프로덕션 서버 기동"""
    print("[2단계] waitress 프로덕션 서버 시작 중...", flush=True)
    print(INFO, flush=True)

    # app.py 위치로 이동
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 동일 Python 으로 waitress 실행
    # ── 300명 동시접속 최적화 설정 ──────────────────────────────
    # --threads=32         : 오픈 직후 버스트 트래픽 처리 (기존 16 → 32)
    # --connection-limit=1000 : 300명 x 다중 탭/폴링 고려 (기존 500 → 1000)
    # --channel-timeout=60 : 유휴 커넥션 빠른 해제로 자원 절약 (기존 120 → 60)
    # --asyncore-use-poll  : select() → poll() 전환 (FD 1024 제한 우회, Linux/Mac)
    cmd = [
        sys.executable, '-m', 'waitress',
        '--host=0.0.0.0',
        '--port=5000',
        '--threads=32',
        '--connection-limit=1000',
        '--channel-timeout=60',
        '--asyncore-use-poll',
        'app:app'
    ]
    subprocess.run(cmd)


if __name__ == '__main__':
    print(BANNER, flush=True)

    python_path = sys.executable
    python_ver = sys.version.split()[0]
    print(f"  Python : {python_path}")
    print(f"  버전   : {python_ver}")
    print()

    install_packages()

    if not verify_waitress():
        print()
        print("[ERROR] waitress 설치에 실패했습니다.")
        print(f"  다음 명령으로 수동 설치 후 다시 실행하세요:")
        print(f"  {python_path} -m pip install waitress")
        sys.exit(1)

    start_server()

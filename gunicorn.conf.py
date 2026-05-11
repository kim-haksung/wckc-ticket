# gunicorn.conf.py — Linux 배포용 설정 (Windows에서는 start.bat/waitress 사용)
#
# ⚠️  중요: workers=1 고정
#   큐(_active, _waiting)가 Python in-memory 구조체이므로
#   워커가 2개 이상이면 메모리가 분리되어 대기열이 동작하지 않습니다.
#   대신 threads=16으로 동시 요청을 처리합니다.

bind         = "0.0.0.0:5000"
workers      = 1          # 반드시 1 — 멀티 워커 시 큐 메모리 분리 문제 발생
worker_class = "sync"
threads      = 16         # 동시 처리 스레드 수 (200명 기준 충분)
timeout      = 120
keepalive    = 5

preload_app  = True       # 앱 1회 로드 후 fork (init_db 중복 방지)

accesslog    = "-"
errorlog     = "-"
loglevel     = "info"

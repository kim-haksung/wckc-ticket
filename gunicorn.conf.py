# gunicorn.conf.py — Linux 배포용 설정 (Windows에서는 start.bat/waitress 사용)
import multiprocessing

bind        = "0.0.0.0:5000"
workers     = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
threads     = 4
timeout     = 120
keepalive   = 5

# preload_app=True: 마스터 프로세스가 앱을 1회만 로드 후 fork
# → init_db()가 포크 이전에 1회만 실행되어 경쟁 조건 방지
preload_app = True

accesslog  = "-"
errorlog   = "-"
loglevel   = "info"

@echo off
chcp 65001 > nul
echo =============================================
echo    공연 티켓 예매 시스템 시작 (운영 서버)
echo =============================================
echo.

echo [1단계] 필수 패키지 설치 중...
python -m pip install flask openpyxl waitress werkzeug -q
echo.

echo [2단계] waitress 프로덕션 서버 시작 중...
echo.
echo  접속 주소: http://127.0.0.1:5000
echo  관리자 ID: admin
echo  관리자 PW: Admin1234!
echo  서버 모드: PRODUCTION (운영)
echo  동시처리:  16 스레드
echo.
echo =============================================
echo  서버를 종료하려면 이 창을 닫거나 Ctrl+C 를 누르세요.
echo =============================================
echo.

python -m waitress --host=0.0.0.0 --port=5000 --threads=16 --connection-limit=500 --channel-timeout=120 app:app
pause

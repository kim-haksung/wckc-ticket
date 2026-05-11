@echo off
chcp 65001 > nul
echo =============================================
echo    공연 티켓 예매 시스템 - 개발 모드
echo =============================================
echo.
echo  [주의] 이 모드는 개발/테스트 전용입니다.
echo  운영 서버에서는 start.bat 을 사용하세요!
echo.
echo  접속 주소: http://127.0.0.1:5000
echo  서버 모드: DEBUG (개발)
echo.
echo =============================================
echo.
set FLASK_DEBUG=1
python app.py
pause

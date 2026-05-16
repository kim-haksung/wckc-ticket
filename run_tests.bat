@echo off
chcp 65001 > nul
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║     티켓 예매 시스템 — 테스트 하네스 실행기         ║
echo ╚══════════════════════════════════════════════════════╝
echo.

:: 패키지 설치 확인
pip show pytest >nul 2>&1
if errorlevel 1 (
    echo [설치] pytest + pytest-flask + pytest-cov 설치 중...
    pip install pytest pytest-flask pytest-cov
)

echo [선택] 실행할 테스트를 선택하세요:
echo   1. 전체 테스트 실행
echo   2. 인증 API (test_auth)
echo   3. 대기열 API (test_queue)
echo   4. 좌석 API   (test_seats)
echo   5. 예매 API   (test_reservations) ← 동시성 포함
echo   6. 관리자 API (test_admin)
echo   7. 전체 + 커버리지 리포트
echo.
set /p choice=번호 입력 (기본: 1):

if "%choice%"=="2" (
    pytest tests/test_auth.py -v
) else if "%choice%"=="3" (
    pytest tests/test_queue.py -v
) else if "%choice%"=="4" (
    pytest tests/test_seats.py -v
) else if "%choice%"=="5" (
    pytest tests/test_reservations.py -v
) else if "%choice%"=="6" (
    pytest tests/test_admin.py -v
) else if "%choice%"=="7" (
    pytest --cov=app --cov-report=term-missing --cov-report=html
    echo.
    echo [완료] 커버리지 리포트: htmlcov/index.html
) else (
    pytest -v
)

echo.
pause

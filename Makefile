# ============================================================
#  Makefile — 온라인 티켓 예매 시스템 테스트 실행
# ============================================================
#
# 왜 python3 -B 인가?
#   virtiofs(Windows<->Linux) 마운트는 mtime 해상도가 1초 단위.
#   같은 초 안에 파일이 두 번 쓰이면 Python이 old .pyc를 재사용.
#   -B 플래그로 bytecode 읽기/쓰기를 완전히 우회.
#
# 왜 scripts/verify_tests.py 인가?
#   bash heredoc + 한국어 UTF-8 조합으로 파일이 중간에 잘릴 수 있음.
#   pytest 진입 전 AST 구문 검증으로 손상 파일을 사전 차단.
#
# ============================================================

.PHONY: test verify clean-pyc

# 기본: 검증 후 전체 테스트 실행
test:
	python3 scripts/verify_tests.py --run

# 검증만 (pytest 실행 없음)
verify:
	python3 scripts/verify_tests.py

# 특정 파일만 실행 (예: make run FILE=tests/test_auth.py)
run:
	python3 -B -m pytest $(FILE) -v

# pyc 강제 무효화 (내용을 0바이트로 덮어써서 Python이 재컴파일하게 함)
clean-pyc:
	@echo "pyc 무효화 중..."
	@find tests/__pycache__ -name "*.pyc" -exec python3 -c \
	  "import sys; [open(f,'wb').close() for f in sys.argv[1:]]" {} + 2>/dev/null || true
	@echo "완료 (다음 실행 시 Python이 재컴파일합니다)"

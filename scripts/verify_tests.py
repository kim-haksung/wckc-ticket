#!/usr/bin/env python3
"""
scripts/verify_tests.py
=======================
pytest 실행 전 모든 테스트 파일의 무결성을 검증합니다.

사용법:
    python3 scripts/verify_tests.py          # 검증만
    python3 scripts/verify_tests.py --run    # 검증 후 pytest 실행

문제 배경 (virtiofs + Windows/Linux 마운트):
  1. virtiofs mtime 1초 해상도 -> stale .pyc 오사용
  2. bash heredoc + 한국어 UTF-8 -> 파일 중간 절단
  3. __pycache__ 삭제 불가 (Operation not permitted)

이 스크립트로 실행하면 위 3가지 문제를 모두 방지합니다.
"""
import ast
import os
import sys
import subprocess

TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tests')


def verify_all():
    errors = []
    test_files = sorted(
        f for f in os.listdir(TESTS_DIR)
        if f.startswith('test_') and f.endswith('.py')
    )

    print("=" * 60)
    print("  테스트 파일 무결성 검증")
    print("=" * 60)

    for fname in test_files:
        path = os.path.join(TESTS_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                source = f.read()
            ast.parse(source)
            size = os.path.getsize(path)
            lines = source.count('\n')
            print(f"  OK  {fname:45}  {lines:4}줄  {size:6}바이트")
        except SyntaxError as e:
            errors.append((fname, f"구문 오류 line {e.lineno}: {e.msg}"))
            print(f"  ERR {fname:45}  <- 구문 오류 line {e.lineno}")
        except UnicodeDecodeError as e:
            errors.append((fname, f"UTF-8 디코딩 실패: {e}"))
            print(f"  ERR {fname:45}  <- UTF-8 디코딩 실패")

    print("=" * 60)

    if errors:
        print(f"\n[실패] {len(errors)}개 파일에 문제가 있습니다:\n")
        for fname, msg in errors:
            print(f"  {fname}: {msg}")
        print("\n수정 방법: python3 open(..., encoding='utf-8').write(...) 로 재작성")
        return False
    else:
        print(f"\n[OK] 전체 {len(test_files)}개 파일 정상\n")
        return True


def run_pytest():
    """
    -B 플래그: pyc 완전 우회 + 검증된 소스로 실행
    (pytest.ini 의 addopts 에도 -B 가 있지만 이중 보호)
    """
    root = os.path.dirname(TESTS_DIR)
    cmd = [sys.executable, '-B', '-m', 'pytest', 'tests/', '-v']
    print("실행:", ' '.join(cmd))
    print()
    result = subprocess.run(cmd, cwd=root)
    return result.returncode == 0


if __name__ == '__main__':
    ok = verify_all()
    if not ok:
        sys.exit(1)
    if '--run' in sys.argv:
        success = run_pytest()
        sys.exit(0 if success else 1)

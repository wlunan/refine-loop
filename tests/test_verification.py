"""
可验证工具集（verification）单元测试

离线测试 CommandRunner 的命令执行、超时、截断与工具构建，
不依赖真实 LLM。
"""

import os
import sys
import tempfile

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"
    ),
)

from src.tools.verification import CommandRunner, build_verification_tools


class TestCommandRunner:
    def test_run_success(self):
        runner = CommandRunner(tempfile.mkdtemp())
        result = runner.run("echo hello")
        assert result.success is True
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_run_failure_exit_code(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "fail.py"), "w", encoding="utf-8") as f:
            f.write("import sys\nsys.exit(3)\n")
        runner = CommandRunner(d)
        result = runner.run_python("fail.py")
        assert result.exit_code == 3
        assert result.success is False

    def test_run_tests_pass(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "test_tmp.py"), "w", encoding="utf-8") as f:
            f.write("def test_ok():\n    assert 1 == 1\n")
        runner = CommandRunner(d)
        result = runner.run_tests()
        assert result.success is True

    def test_run_python_stdout(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
            f.write("print('ok')\n")
        runner = CommandRunner(d)
        result = runner.run_python("main.py")
        assert result.success is True
        assert "ok" in result.stdout

    def test_output_truncation(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "big.py"), "w", encoding="utf-8") as f:
            f.write("print('A' * 200)\n")
        runner = CommandRunner(d, max_output_chars=50)
        result = runner.run_python("big.py")
        assert "已截断" in result.stdout

    def test_timeout(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "sleep.py"), "w", encoding="utf-8") as f:
            f.write("import time\ntime.sleep(5)\n")
        runner = CommandRunner(d, timeout=1)
        result = runner.run_python("sleep.py")
        assert result.timed_out is True
        assert result.success is False

    def test_build_tools(self):
        runner = CommandRunner(tempfile.mkdtemp())
        tools = build_verification_tools(runner)
        names = {t.name for t in tools}
        assert {"run_command", "run_tests", "run_lint", "run_python"} <= names

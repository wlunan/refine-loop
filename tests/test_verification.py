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

from src.models.run import RunConfig, VerificationStep
from src.tools.verification import CodeVerifier, CommandRunner, build_verification_tools


class TestCommandRunner:
    def test_run_args_success(self):
        runner = CommandRunner(tempfile.mkdtemp())
        result = runner.run_args([sys.executable, "-c", "print('hello')"])
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

    def test_missing_executable_returns_structured_failure(self):
        runner = CommandRunner(tempfile.mkdtemp())
        result = runner.run_args(["generator_critic_missing_executable_12345"])
        assert result.success is False
        assert result.exit_code == -1
        assert "未找到验证命令" in result.stderr

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
        assert {"run_tests", "run_lint", "run_python"} <= names
        assert "run_command" not in names


class TestCodeVerifier:
    def test_profile_builds_pytest_step(self):
        config = RunConfig.from_profile(
            "python_pytest",
            max_rounds=3,
            score_threshold=85,
            round_token_budget=100,
            total_token_budget=200,
        )
        assert config.verification_profile == "python_pytest"
        assert config.verification_steps[0].id == "pytest"

    def test_node_profile_uses_windows_command_shim(self):
        config = RunConfig.from_profile(
            "node_build",
            max_rounds=3,
            score_threshold=85,
            round_token_budget=100,
            total_token_budget=200,
        )
        expected = "npm.cmd" if sys.platform == "win32" else "npm"
        assert config.verification_steps[0].args == [expected, "run", "build"]

    def test_verify_collects_failure_evidence(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "check.py"), "w", encoding="utf-8") as f:
            f.write("import sys\nprint('verification failed')\nsys.exit(2)\n")
        config = RunConfig.from_profile(
            "none",
            max_rounds=1,
            score_threshold=85,
            round_token_budget=100,
            total_token_budget=200,
        )
        config.verification_steps = [
            VerificationStep(
                id="check",
                label="检查脚本",
                command=f'"{sys.executable}" check.py',
                args=[sys.executable, "check.py"],
            )
        ]

        summary = CodeVerifier(d).verify(
            config.verification_steps,
            config.verification_profile,
        )

        assert summary.passed is False
        assert summary.results[0].exit_code == 2
        assert "verification failed" in summary.evidence()

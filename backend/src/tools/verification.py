"""
可验证工具集（Verification Tools）

为 Agent 提供在沙箱内执行真实命令的能力，让「批判」与「修复」基于
真实执行结果（测试是否通过、lint 是否报错、脚本能否运行），
而非纯文本猜测。

这是本项目区别于纯文本多 Agent 审查的关键差异点（CRITIC 式可验证性）：
Critic 不再只说「我觉得这行可能有 bug」，而是能拿到「pytest 第 3 条挂了、
报错是 XXX」这样的事实依据。

工具：
- run_tests:   运行 pytest
- run_lint:    运行 ruff（未安装则回退 flake8）
- run_python:  运行单个 Python 脚本（快速验证可运行性）

安全设计：
- cwd 固定为工作区根目录，命令在工作区内执行
- 超时控制（默认 120s），避免失控进程挂死
- 输出截断（stdout/stderr 各截断到上限），避免撑爆上下文
- 返回结构化结果（exit_code / stdout / stderr / timed_out）
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List

from langchain_core.tools import tool

from src.models.run import VerificationResult, VerificationStep, VerificationSummary


@dataclass
class CommandResult:
    """命令执行结果（结构化，便于 Agent 与上层逻辑消费）"""

    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        """是否执行成功（退出码为 0 且未超时）"""
        return self.exit_code == 0 and not self.timed_out

    def to_str(self) -> str:
        """格式化为面向 LLM 的文本"""
        lines = [f"退出码: {self.exit_code}"]
        if self.timed_out:
            lines.append("（命令执行超时，已强制终止）")
        if self.stdout:
            lines.append(f"【标准输出】\n{self.stdout}")
        if self.stderr:
            lines.append(f"【标准错误】\n{self.stderr}")
        return "\n".join(lines)


class CommandRunner:
    """
    在工作区沙箱内执行真实命令的 runner

    Args:
        workspace_root: 工作区根目录（绝对路径），命令的 cwd
        timeout: 单条命令超时时间（秒）
        max_output_chars: stdout/stderr 各自的截断上限（字符）
    """

    def __init__(
        self,
        workspace_root: str,
        timeout: int = 120,
        max_output_chars: int = 8000,
    ):
        self.workspace_root = workspace_root
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def _truncate(self, text: str) -> str:
        if len(text) > self.max_output_chars:
            return (
                text[: self.max_output_chars]
                + f"\n... [已截断，总长度 {len(text)} 字符]"
            )
        return text

    def _safe_workspace_path(self, path: str) -> str:
        """Resolve an Agent-supplied path and reject paths outside the worktree."""
        candidate = os.path.realpath(os.path.join(self.workspace_root, path))
        root = os.path.realpath(self.workspace_root)
        if os.path.commonpath([root, candidate]) != root:
            raise ValueError(f"验证路径越界: {path}")
        return candidate

    def run(self, command: str) -> CommandResult:
        """
        在工作区目录内执行一条 shell 命令

        Args:
            command: 要执行的命令字符串

        Returns:
            CommandResult（含退出码 / stdout / stderr）
        """
        started_at = time.monotonic()
        try:
            proc = subprocess.run(
                shlex.split(command),
                shell=False,
                cwd=self.workspace_root,
                timeout=self.timeout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return CommandResult(
                command=command,
                exit_code=proc.returncode,
                stdout=self._truncate(proc.stdout or ""),
                stderr=self._truncate(proc.stderr or ""),
                duration_seconds=time.monotonic() - started_at,
            )
        except subprocess.TimeoutExpired as e:
            stdout = ""
            if e.stdout is not None:
                stdout = (
                    e.stdout.decode("utf-8", errors="replace")
                    if isinstance(e.stdout, bytes)
                    else str(e.stdout)
                )
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout=self._truncate(stdout),
                stderr=f"命令执行超时（>{self.timeout}s），已强制终止",
                timed_out=True,
                duration_seconds=time.monotonic() - started_at,
            )

    def run_args(self, args: list[str]) -> CommandResult:
        """以 shell=False 执行受控参数列表，供内置验证 profile 使用。"""
        started_at = time.monotonic()
        try:
            proc = subprocess.run(
                args,
                shell=False,
                cwd=self.workspace_root,
                timeout=self.timeout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return CommandResult(
                command=" ".join(args),
                exit_code=proc.returncode,
                stdout=self._truncate(proc.stdout or ""),
                stderr=self._truncate(proc.stderr or ""),
                duration_seconds=time.monotonic() - started_at,
            )
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else str(e.stdout or "")
            return CommandResult(
                command=" ".join(args),
                exit_code=-1,
                stdout=self._truncate(stdout),
                stderr=f"命令执行超时（{self.timeout}s），已强制终止",
                timed_out=True,
                duration_seconds=time.monotonic() - started_at,
            )

    def run_tests(self, path: str = ".", extra_args: str = "") -> CommandResult:
        """
        运行 pytest 单元测试

        使用当前解释器（sys.executable）的 `-m pytest`，确保测试环境
        与运行环境一致。

        Args:
            path: 测试路径（相对工作区根目录）
            extra_args: 额外的 pytest 参数

        Returns:
            CommandResult（exit_code 0 表示全部通过，1 表示有失败）
        """
        safe_path = self._safe_workspace_path(path)
        return self.run_args(
            [sys.executable, "-m", "pytest", safe_path, "-q", *shlex.split(extra_args)]
        )

    def run_lint(self, path: str = ".") -> CommandResult:
        """
        运行代码规范检查（ruff，未安装则回退 flake8）

        Args:
            path: 检查路径（相对工作区根目录）

        Returns:
            CommandResult
        """
        safe_path = self._safe_workspace_path(path)
        result = self.run_args([sys.executable, "-m", "ruff", "check", safe_path])
        # ruff 未安装时（ModuleNotFoundError）回退 flake8
        if "No module named ruff" in result.stderr:
            return self.run_args([sys.executable, "-m", "flake8", safe_path])
        return result

    def run_python(self, script_path: str) -> CommandResult:
        """
        运行工作区内的一个 Python 脚本，快速验证可运行性

        Args:
            script_path: 脚本相对路径

        Returns:
            CommandResult
        """
        return self.run_args([sys.executable, self._safe_workspace_path(script_path)])


class CodeVerifier:
    """按运行配置执行一组确定性验证步骤。"""

    def __init__(self, workspace_root: str, max_output_chars: int = 8000):
        self.workspace_root = workspace_root
        self.max_output_chars = max_output_chars

    def verify(
        self,
        steps: list[VerificationStep],
        profile: str = "none",
    ) -> VerificationSummary:
        """顺序执行验证并返回可持久化的汇总结果。"""
        results: list[VerificationResult] = []
        for step in steps:
            runner = CommandRunner(
                self.workspace_root,
                timeout=step.timeout_seconds,
                max_output_chars=self.max_output_chars,
            )
            # 复用既有 lint 降级：环境没有 ruff 时尝试 flake8，避免标准
            # lint profile 因工具缺失而失去可用性。
            if step.args:
                command_result = runner.run_args(step.args)
            elif step.id == "ruff":
                command_result = runner.run_lint()
            else:
                command_result = CommandResult(
                    command=step.command,
                    exit_code=2,
                    stderr="验证步骤缺少受控参数列表，已拒绝执行。",
                )
            results.append(
                VerificationResult(
                    step_id=step.id,
                    label=step.label,
                    required=step.required,
                    passed=command_result.success,
                    exit_code=command_result.exit_code,
                    stdout=command_result.stdout,
                    stderr=command_result.stderr,
                    timed_out=command_result.timed_out,
                    duration_seconds=command_result.duration_seconds,
                )
            )
        return VerificationSummary(profile=profile, results=results)


def build_verification_tools(runner: CommandRunner) -> list:
    """
    基于一个 CommandRunner 实例生成 LangChain 工具列表

    这些工具既可用于原生 tool calling（llm.bind_tools），
    也可通过 name 手动分派（JSON 文本协议降级）。

    Args:
        runner: 命令执行器实例

    Returns:
        LangChain StructuredTool 列表
    """

    @tool
    def run_command(command: str) -> str:
        """在工作区目录内执行一条 shell 命令，返回退出码、标准输出与标准错误。用于运行测试、构建、脚本等验证操作。"""
        return runner.run(command).to_str()

    @tool
    def run_tests(path: str = ".") -> str:
        """在工作区目录内运行 pytest 单元测试，返回测试结果（通过或失败详情）。path 为相对工作区根目录的测试路径。"""
        return runner.run_tests(path).to_str()

    @tool
    def run_lint(path: str = ".") -> str:
        """在工作区目录内运行 ruff（未安装则回退 flake8）代码规范检查，返回检查结果。"""
        return runner.run_lint(path).to_str()

    @tool
    def run_python(script_path: str) -> str:
        """运行工作区内的一个 Python 脚本并返回执行结果，用于快速验证代码能否运行。script_path 为相对工作区根目录的路径。"""
        return runner.run_python(script_path).to_str()

    # Agent-facing verification is limited to fixed executables and sandboxed paths.
    return [run_tests, run_lint, run_python]

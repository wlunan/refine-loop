"""
Benchmark 评测执行器

对比两种策略在同一任务上的客观表现（以 ground truth 测试是否通过为准）：
- baseline：       Generator 单次生成实现，不验证、不迭代
- self_healing：   代码自愈闭环（生成 → 验证 → 失败定位 → 修复 → 复跑）

评测的客观指标是 pytest 测试通过与否，而非 Critic 的主观评分。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from src.agents.generator import GeneratorAgent
from src.orchestrator import SelfHealingOrchestrator
from src.tools.verification import CommandRunner


@dataclass
class StrategyResult:
    """单个策略在单个任务上的结果"""

    passed: bool
    exit_code: int
    rounds: int = 1
    detail: str = ""


@dataclass
class TaskResult:
    """单个任务在两种策略下的对比结果"""

    task_name: str
    baseline: StrategyResult
    self_healing: StrategyResult

    @property
    def repaired(self) -> bool:
        """baseline 失败、自愈后通过（即「被自愈闭环修复」的任务）"""
        return not self.baseline.passed and self.self_healing.passed


def _write_test(workspace: str, task: dict) -> None:
    """把任务的 ground truth 测试写入 workspace"""
    with open(os.path.join(workspace, task["test_file"]), "w", encoding="utf-8") as f:
        f.write(task["test_code"])


def evaluate_baseline(task: dict, generator: Optional[GeneratorAgent] = None) -> StrategyResult:
    """
    单次生成：Generator 生成一次实现，不验证、不迭代，随后运行测试。

    对应「一次 LLM 调用出结果」的传统做法，作为对比基线。
    """
    workspace = tempfile.mkdtemp(prefix=f"bench_{task['name']}_base_")
    _write_test(workspace, task)

    gen = generator or GeneratorAgent(domain="code")
    gen.generate_with_files(
        task=task["description"],
        workspace_dir=workspace,
        enable_verification=False,  # 关键：单次生成，不让它自己验证
    )

    result = CommandRunner(workspace).run_tests()
    return StrategyResult(
        passed=result.success,
        exit_code=result.exit_code,
        rounds=1,
        detail=result.to_str(),
    )


def evaluate_self_healing(
    task: dict,
    generator: Optional[GeneratorAgent] = None,
    max_repair_rounds: int = 3,
) -> StrategyResult:
    """
    自愈闭环：生成 → 验证 → 失败定位 → 修复 → 复跑，直到测试通过或达到上限。
    """
    workspace = tempfile.mkdtemp(prefix=f"bench_{task['name']}_heal_")
    _write_test(workspace, task)

    orch = SelfHealingOrchestrator(
        generator=generator,
        workspace_dir=workspace,
        verify_command="pytest",
        max_repair_rounds=max_repair_rounds,
        domain="code",
    )
    result = orch.run(task["description"])

    final = result.final_verification
    return StrategyResult(
        passed=result.success,
        exit_code=final.exit_code if final else -1,
        rounds=result.repair_rounds,
        detail=final.to_str() if final else "",
    )


def run_all(tasks: List[dict], generator: Optional[GeneratorAgent] = None) -> List[TaskResult]:
    """依次评测所有任务，返回结果列表（generator 复用以避免重复初始化 LLM）"""
    gen = generator or GeneratorAgent(domain="code")
    results: List[TaskResult] = []
    for task in tasks:
        baseline = evaluate_baseline(task, gen)
        healing = evaluate_self_healing(task, gen)
        results.append(TaskResult(task["name"], baseline, healing))
    return results

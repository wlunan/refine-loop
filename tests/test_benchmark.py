"""
Benchmark 单元测试（离线，不依赖 LLM）

只测测试集结构与报告统计逻辑，不实际调用模型。
"""

import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"
    ),
)

from benchmark.tasks import TASKS
from benchmark.runner import StrategyResult, TaskResult
from benchmark.report import generate_report


class TestTasks:
    def test_tasks_complete(self):
        assert len(TASKS) >= 3
        for task in TASKS:
            assert "name" in task
            assert "description" in task
            assert "test_file" in task
            assert "test_code" in task
            # 测试文件名应包含实现模块名（保证 import 路径一致）
            assert task["name"] in task["test_file"]

    def test_test_code_imports_module(self):
        for task in TASKS:
            # ground truth 测试应 import 对应实现模块
            assert f"from {task['name']} import" in task["test_code"]


class TestReport:
    @staticmethod
    def _make_result(baseline_passed, healing_passed, rounds=2):
        return TaskResult(
            "task",
            StrategyResult(
                passed=baseline_passed,
                exit_code=0 if baseline_passed else 1,
            ),
            StrategyResult(
                passed=healing_passed,
                exit_code=0 if healing_passed else 1,
                rounds=rounds,
            ),
        )

    def test_repair_rate(self):
        results = [
            self._make_result(True, True),    # baseline 已通过
            self._make_result(False, True),   # 被自愈修复
            self._make_result(False, False),  # 未被修复
        ]
        report = generate_report(results)
        assert "66.7%" in report   # self-healing 通过率 2/3
        assert "50.0%" in report   # 修复率 1/2

    def test_repaired_property(self):
        assert self._make_result(False, True).repaired is True
        assert self._make_result(True, True).repaired is False
        assert self._make_result(False, False).repaired is False

    def test_empty_report(self):
        assert "无评测结果" in generate_report([])

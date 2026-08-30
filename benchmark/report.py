"""
Benchmark 报告生成

把评测结果汇总为 Markdown 报告，核心指标：
- baseline 通过率 vs self_healing 通过率
- 修复率（baseline 失败但自愈后通过的任务占比）
- 平均修复轮数
"""

from __future__ import annotations

from typing import List

from .runner import TaskResult


def generate_report(results: List[TaskResult]) -> str:
    """生成 Markdown 格式的评测报告"""
    total = len(results)
    if total == 0:
        return "（无评测结果）"

    baseline_passed = sum(1 for r in results if r.baseline.passed)
    healing_passed = sum(1 for r in results if r.self_healing.passed)
    repaired = sum(1 for r in results if r.repaired)
    baseline_failed = sum(1 for r in results if not r.baseline.passed)

    repair_rate = (repaired / baseline_failed * 100) if baseline_failed else 0.0
    avg_rounds = (
        sum(r.self_healing.rounds for r in results) / total if total else 0.0
    )

    lines: List[str] = []
    lines.append("# Benchmark 评测报告")
    lines.append("")
    lines.append("> 客观指标：ground truth 单元测试通过与否（非 Critic 主观评分）")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| 指标 | Baseline（单次生成） | Self-Healing（自愈闭环） |")
    lines.append("|------|---------------------|--------------------------|")
    lines.append(
        f"| 测试通过率 | {baseline_passed}/{total} "
        f"({baseline_passed / total * 100:.1f}%) | {healing_passed}/{total} "
        f"({healing_passed / total * 100:.1f}%) |"
    )
    lines.append("")
    lines.append(f"- **修复率**：{repaired}/{baseline_failed}（{repair_rate:.1f}%）——baseline 失败、自愈后通过的任务占比")
    lines.append(f"- **平均修复轮数**：{avg_rounds:.1f} 轮")
    lines.append("")
    lines.append("## 逐任务明细")
    lines.append("")
    lines.append("| 任务 | Baseline | Self-Healing | 修复轮数 | 是否被自愈修复 |")
    lines.append("|------|----------|--------------|----------|----------------|")
    for r in results:
        base_mark = "✅" if r.baseline.passed else "❌"
        heal_mark = "✅" if r.self_healing.passed else "❌"
        repaired_mark = "✅" if r.repaired else "—"
        lines.append(
            f"| {r.task_name} | {base_mark} | {heal_mark} "
            f"| {r.self_healing.rounds} | {repaired_mark} |"
        )
    lines.append("")
    lines.append("## 结论")
    lines.append("")
    if healing_passed > baseline_passed:
        lines.append(
            f"自愈闭环将测试通过率从 **{baseline_passed}/{total}** 提升到 "
            f"**{healing_passed}/{total}**，修复率 {repair_rate:.1f}%，"
            f"验证了「生成 → 验证 → 修复 → 复跑」闭环的价值。"
        )
    else:
        lines.append(
            "自愈闭环未带来通过率提升，可能原因：模型能力不足、任务过难、"
            "或修复轮数上限过低，建议调整参数后重跑。"
        )
    lines.append("")
    return "\n".join(lines)

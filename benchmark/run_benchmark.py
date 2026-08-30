"""
Benchmark 入口

运行完整评测：对测试集中的每个任务，对比「单次生成（baseline）」与
「自愈闭环（self-healing）」的测试通过率，输出 Markdown 报告并保存。

用法：
    python benchmark/run_benchmark.py
"""

import os
import sys

# 添加项目根目录与 backend 到路径
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"
    ),
)

from config.settings import setup_logging
from benchmark.tasks import TASKS
from benchmark.runner import run_all
from benchmark.report import generate_report


def main():
    setup_logging()
    print(f"开始评测 {len(TASKS)} 个任务（每任务对比 baseline 与自愈闭环）...")
    print("=" * 60)

    results = run_all(TASKS)

    report = generate_report(results)
    print("\n" + report)

    # 保存报告
    report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "latest_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已保存到: {report_path}")


if __name__ == "__main__":
    main()

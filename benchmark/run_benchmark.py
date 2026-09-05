"""
Benchmark 入口

运行完整评测：对测试集中的每个任务，对比「单次生成（baseline）」与
「自愈闭环（self-healing）」的测试通过率，输出 Markdown 报告并保存。

用法：
    python benchmark/run_benchmark.py
"""

import argparse
import os
import sys
from datetime import datetime

# 添加项目根目录与 backend 到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from config.settings import setup_logging
from benchmark.tasks import TASKS
from benchmark.runner import run_all
from benchmark.report import generate_report
from benchmark.artifacts import build_run_artifact, write_artifact


def main():
    parser = argparse.ArgumentParser(description="Run the Generator-Critic benchmark")
    parser.add_argument("--max-repair-rounds", type=int, default=3)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    setup_logging()
    print(f"开始评测 {len(TASKS)} 个任务（每任务对比 baseline 与自愈闭环）...")
    print("=" * 60)

    results = run_all(TASKS, max_repair_rounds=args.max_repair_rounds)

    report = generate_report(results)
    print("\n" + report)

    # 保存报告
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "results", run_id
    )
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    artifact_path = write_artifact(
        report_dir,
        build_run_artifact(results, max_repair_rounds=args.max_repair_rounds),
    )
    print(f"原始结果已保存到: {artifact_path}")
    print(f"\n报告已保存到: {report_path}")


if __name__ == "__main__":
    main()

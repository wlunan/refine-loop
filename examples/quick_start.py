"""
快速开始示例
展示最基本的 Generator-Critic 使用方式，
并实时打印每一轮的 Generator 产出与 Critic 审查内容
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestrator import Orchestrator
from src.models.schemas import CritiqueResult


def on_round_complete(round_num: int, draft: str, critique: CritiqueResult):
    """每轮迭代完成时，实时打印 Generator 产出与 Critic 审查内容"""
    print(f"\n{'=' * 50}")
    print(f"第 {round_num} 轮")
    print(f"{'=' * 50}")

    print("\n[Generator 产出]")
    print(draft)

    print("\n[Critic 审查]")
    print(f"评分: {critique.score} / 100  可接受: {'是' if critique.acceptable else '否'}")

    if critique.issues:
        print("问题:")
        for i, issue in enumerate(critique.issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("问题: 无")

    if critique.suggestions:
        print("建议:")
        for i, sug in enumerate(critique.suggestions, 1):
            print(f"  {i}. {sug}")

    if critique.summary:
        print(f"总结: {critique.summary}")
    print()


def main():
    # 1. 创建编排器（指定领域和最大轮数，注册逐轮回调）
    orchestrator = Orchestrator(
        domain="general",  # 可选: general/code/writing/design
        max_rounds=3,
        on_round_complete=on_round_complete,
    )

    # 2. 定义任务
    task = "写一篇关于'为什么要学习编程'的短文，300字左右"

    # 3. 运行
    print(f"任务: {task}\n")
    print("=" * 50)
    print("开始 Generator-Critic 迭代...")
    print("=" * 50)

    result = orchestrator.run(task)

    # 4. 输出最终结果
    print("\n" + "=" * 50)
    print("最终产出:")
    print("=" * 50)
    print(result.final_output)

    # 5. 输出运行摘要
    print("\n" + result.summary())


if __name__ == "__main__":
    main()

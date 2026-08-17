"""
代码审查示例
使用 Generator-Critic 模式生成并优化代码
领域: code
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import setup_logging
from src.orchestrator import Orchestrator
from src.models.schemas import CritiqueResult


def on_iteration_complete(round_num: int, critique: CritiqueResult) -> None:
    """每轮迭代完成后的回调，用于实时展示进度"""
    print(f"\n--- 第 {round_num} 轮审查结果 ---")
    print(f"评分: {critique.score}/100")
    print(f"可接受: {'是' if critique.acceptable else '否'}")
    if critique.issues:
        print("问题:")
        for i, issue in enumerate(critique.issues, 1):
            print(f"  {i}. {issue}")
    if critique.suggestions:
        print("建议:")
        for i, sug in enumerate(critique.suggestions, 1):
            print(f"  {i}. {sug}")


def main():
    setup_logging()
    # 创建代码领域的编排器
    orchestrator = Orchestrator(
        domain="code",
        max_rounds=4,
        on_iteration_complete=on_iteration_complete,
    )

    # 定义代码生成任务
    task = """
实现一个 Python 的 LRU 缓存类，要求：
1. 使用字典 + 双向链表实现，get 和 put 操作都是 O(1)
2. 支持指定容量
3. 包含类型注解和文档字符串
4. 包含边界条件处理（空缓存、容量为1等）
5. 写一个简单的使用示例
    """.strip()

    print("=" * 60)
    print("代码生成与审查示例 - LRU 缓存")
    print("=" * 60)
    print(f"\n任务:\n{task}\n")

    # 运行
    result = orchestrator.run(task)

    # 输出最终代码
    print("\n" + "=" * 60)
    print("最终代码:")
    print("=" * 60)
    print(result.final_output)

    # 输出摘要
    print("\n" + result.summary())

    # 输出评分趋势分析
    print("\n评分趋势分析:")
    trend = result.score_trend
    if len(trend) >= 2:
        improvement = trend[-1] - trend[0]
        print(f"  初始评分: {trend[0]}")
        print(f"  最终评分: {trend[-1]}")
        print(f"  提升: {improvement:+d} 分")
        if improvement > 0:
            print("  结论: 迭代优化有效，代码质量有提升")
        else:
            print("  结论: 迭代未带来明显提升，可能初始版本已较好或需要更多轮次")


if __name__ == "__main__":
    main()

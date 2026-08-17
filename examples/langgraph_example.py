"""
LangGraph 版本使用示例
展示基于图状态机的 Generator-Critic 工作流
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import setup_logging
from src.graph import GeneratorCriticGraph


def main():
    setup_logging()
    # 创建基于 LangGraph 的工作流
    graph = GeneratorCriticGraph(
        domain="code",
        max_rounds=3,
        score_threshold=85,
    )

    # 定义任务
    task = "用 Python 实现一个二分查找算法，要求处理边界条件并包含类型注解"

    print("=" * 60)
    print("LangGraph 版本示例 - 二分查找")
    print("=" * 60)
    print(f"\n任务: {task}\n")

    # 执行工作流
    final_state = graph.run(task)

    # 输出结果
    print("\n" + "=" * 60)
    print("最终产出:")
    print("=" * 60)
    print(final_state.get("draft", ""))

    # 输出运行信息
    print("\n" + "=" * 60)
    print("运行信息:")
    print("=" * 60)
    print(f"迭代轮数: {final_state.get('current_round', 0)}")
    print(f"是否收敛: {final_state.get('converged', False)}")
    print(f"收敛原因: {final_state.get('convergence_reason', 'N/A')}")

    # 输出评分趋势
    history = final_state.get("history", [])
    if history:
        print("\n评分趋势:")
        for record in history:
            print(f"  第 {record.round} 轮: {record.critique.score} 分")

        # 获取最优版本
        best_draft = graph.get_best_draft(final_state)
        if best_draft != final_state.get("draft"):
            print("\n注意: 最优版本与最终版本不同，最优评分为: "
                  f"{max(r.critique.score for r in history)}")

    # 可选：可视化工作流图（需要安装 graphviz）
    # graph.visualize("workflow.png")


if __name__ == "__main__":
    main()

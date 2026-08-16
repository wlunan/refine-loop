"""
快速开始示例
展示最基本的 Generator-Critic 使用方式
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestrator import Orchestrator


def main():
    # 1. 创建编排器（指定领域和最大轮数）
    orchestrator = Orchestrator(
        domain="general",  # 可选: general/code/writing/design
        max_rounds=3,
    )

    # 2. 定义任务
    task = "写一篇关于'为什么要学习编程'的短文，300字左右"

    # 3. 运行
    print(f"任务: {task}\n")
    print("=" * 50)
    print("开始 Generator-Critic 迭代...")
    print("=" * 50 + "\n")

    result = orchestrator.run(task)

    # 4. 输出结果
    print("\n" + "=" * 50)
    print("最终产出:")
    print("=" * 50)
    print(result.final_output)

    # 5. 输出运行摘要
    print("\n" + result.summary())


if __name__ == "__main__":
    main()

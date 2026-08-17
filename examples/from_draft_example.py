"""
从初始草稿开始优化的示例
展示如何提供已有内容，让 Generator-Critic 进行迭代优化
适用于：已有初稿需要润色、代码需要 review 等场景
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import setup_logging
from src.orchestrator import Orchestrator


def main():
    setup_logging()
    # 初始草稿（用户已有的内容）
    initial_draft = """
def binary_search(arr, target):
    left = 0
    right = len(arr)
    while left < right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid
        else:
            right = mid
    return -1
    """.strip()

    # 任务描述
    task = """
审查并优化以下二分查找代码，要求：
1. 修复可能存在的 bug
2. 添加类型注解和文档字符串
3. 处理边界条件
4. 添加简单的测试用例
    """.strip()

    print("=" * 60)
    print("从初始草稿开始优化示例")
    print("=" * 60)
    print(f"\n初始草稿:\n{initial_draft}\n")
    print(f"任务:\n{task}\n")

    # 创建编排器
    orchestrator = Orchestrator(
        domain="code",
        max_rounds=3,
    )

    # 运行，传入初始草稿
    result = orchestrator.run(task, initial_draft=initial_draft)

    # 输出结果
    print("\n" + "=" * 60)
    print("优化后的代码:")
    print("=" * 60)
    print(result.final_output)

    # 输出对比信息
    print("\n" + "=" * 60)
    print("优化对比:")
    print("=" * 60)
    print(f"初始草稿长度: {len(initial_draft)} 字符")
    print(f"最终版本长度: {len(result.final_output)} 字符")
    print(f"迭代轮数: {result.iterations}")
    print(f"最终评分: {result.state.critique.score if result.state.critique else 'N/A'}")

    # 输出每轮的问题
    print("\n各轮审查问题:")
    for i, record in enumerate(result.state.history, 1):
        print(f"\n  第 {i} 轮 (评分 {record.critique.score}):")
        if record.critique.issues:
            for issue in record.critique.issues:
                print(f"    - {issue}")
        else:
            print("    - 无问题")


if __name__ == "__main__":
    main()

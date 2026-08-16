"""
文案写作示例
使用 Generator-Critic 模式生成并优化文案
领域: writing
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestrator import Orchestrator
from src.models.schemas import CritiqueResult


def main():
    # 创建文案写作领域的编排器
    orchestrator = Orchestrator(
        domain="writing",
        max_rounds=3,
    )

    # 定义文案任务
    task = """
为一款面向大学生的背单词 APP 写一篇小红书推广文案，要求：
1. 标题吸引人，带 emoji
2. 正文 300-500 字
3. 突出产品的核心卖点：艾宾浩斯遗忘曲线复习、离线使用、完全免费
4. 语气亲切，像学姐推荐
5. 结尾带互动引导和话题标签
    """.strip()

    print("=" * 60)
    print("文案写作示例 - 小红书推广文案")
    print("=" * 60)
    print(f"\n任务:\n{task}\n")

    # 运行
    result = orchestrator.run(task)

    # 输出每轮的评分变化
    print("\n迭代过程评分:")
    for i, record in enumerate(result.state.history, 1):
        print(f"  第 {i} 轮: {record.critique.score} 分 "
              f"(问题 {len(record.critique.issues)} 个)")

    # 输出最终文案
    print("\n" + "=" * 60)
    print("最终文案:")
    print("=" * 60)
    print(result.final_output)

    # 输出摘要
    print("\n" + result.summary())


if __name__ == "__main__":
    main()

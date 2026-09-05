"""
Benchmark 测试集

每个任务是一道「用 Python 实现 X」的编码题，评测的客观依据是**预先写好的
ground truth 单元测试**（而非 Critic 的主观评分）：Agent 生成实现代码，评测器
运行这些测试，通过即视为正确。

任务字段：
- name:        任务名（同时是实现模块名）
- description: 任务描述（给 Agent 的 prompt，需明确写入的文件名）
- test_file:   ground truth 测试文件名
- test_code:   ground truth 测试代码（评测器写入 workspace 后运行）
"""

BENCHMARK_VERSION = "2026.09.04.v1"

TASKS = [
    {
        "name": "lru_cache",
        "description": (
            "实现一个 LRU（最近最少使用）缓存类，写入 lru_cache.py 文件。"
            "要求：LRUCache(capacity) 构造函数；get(key) 返回缓存值（不存在返回 -1）；"
            "put(key, value) 插入或更新；get 和 put 需 O(1) 平均时间复杂度；"
            "缓存满时淘汰最久未使用的项。"
        ),
        "test_file": "test_lru_cache.py",
        "test_code": (
            "from lru_cache import LRUCache\n"
            "\n"
            "\n"
            "def test_basic_operations():\n"
            "    cache = LRUCache(2)\n"
            "    cache.put(1, 1)\n"
            "    cache.put(2, 2)\n"
            "    assert cache.get(1) == 1\n"
            "    cache.put(3, 3)  # 淘汰最久未使用的 key 2\n"
            "    assert cache.get(2) == -1\n"
            "    cache.put(4, 4)  # 淘汰 key 1\n"
            "    assert cache.get(1) == -1\n"
            "    assert cache.get(3) == 3\n"
            "    assert cache.get(4) == 4\n"
            "\n"
            "\n"
            "def test_update_existing():\n"
            "    cache = LRUCache(2)\n"
            "    cache.put(1, 1)\n"
            "    cache.put(1, 10)\n"
            "    assert cache.get(1) == 10\n"
            "\n"
            "\n"
            "def test_capacity_one():\n"
            "    cache = LRUCache(1)\n"
            "    cache.put(1, 1)\n"
            "    cache.put(2, 2)\n"
            "    assert cache.get(1) == -1\n"
            "    assert cache.get(2) == 2\n"
        ),
    },
    {
        "name": "binary_search",
        "description": (
            "实现二分查找函数，写入 binary_search.py 文件。"
            "要求：binary_search(nums, target) 在升序数组 nums 中查找 target，"
            "返回其下标；若不存在返回 -1。需处理空数组与边界情况。"
        ),
        "test_file": "test_binary_search.py",
        "test_code": (
            "from binary_search import binary_search\n"
            "\n"
            "\n"
            "def test_found_middle():\n"
            "    assert binary_search([1, 2, 3, 4, 5], 3) == 2\n"
            "\n"
            "\n"
            "def test_found_boundaries():\n"
            "    assert binary_search([1, 2, 3, 4, 5], 1) == 0\n"
            "    assert binary_search([1, 2, 3, 4, 5], 5) == 4\n"
            "\n"
            "\n"
            "def test_not_found():\n"
            "    assert binary_search([1, 2, 3, 4, 5], 6) == -1\n"
            "\n"
            "\n"
            "def test_empty_list():\n"
            "    assert binary_search([], 1) == -1\n"
        ),
    },
    {
        "name": "reverse_linked_list",
        "description": (
            "实现单链表反转，写入 reverse_linked_list.py 文件。"
            "要求：定义 ListNode 类（val 和 next 属性），以及 reverse_list(head) "
            "函数，返回反转后的链表头节点。空链表返回 None。"
        ),
        "test_file": "test_reverse_linked_list.py",
        "test_code": (
            "from reverse_linked_list import ListNode, reverse_list\n"
            "\n"
            "\n"
            "def _build(values):\n"
            "    head = None\n"
            "    for v in reversed(values):\n"
            "        head = ListNode(v, head)\n"
            "    return head\n"
            "\n"
            "\n"
            "def _to_list(head):\n"
            "    result = []\n"
            "    while head:\n"
            "        result.append(head.val)\n"
            "        head = head.next\n"
            "    return result\n"
            "\n"
            "\n"
            "def test_reverse_three():\n"
            "    assert _to_list(reverse_list(_build([1, 2, 3]))) == [3, 2, 1]\n"
            "\n"
            "\n"
            "def test_reverse_single():\n"
            "    assert _to_list(reverse_list(_build([1]))) == [1]\n"
            "\n"
            "\n"
            "def test_reverse_empty():\n"
            "    assert reverse_list(None) is None\n"
        ),
    },
    {
        "name": "valid_parentheses",
        "description": (
            "实现括号匹配校验函数，写入 valid_parentheses.py 文件。"
            "要求：is_valid(s) 判断字符串 s 中的括号是否有效（'()'、'[]'、'{}' 正确"
            "配对且闭合顺序正确），返回布尔值。空字符串视为有效。"
        ),
        "test_file": "test_valid_parentheses.py",
        "test_code": (
            "from valid_parentheses import is_valid\n"
            "\n"
            "\n"
            "def test_valid_cases():\n"
            "    assert is_valid('()') is True\n"
            "    assert is_valid('()[]{}') is True\n"
            "    assert is_valid('{[]}') is True\n"
            "\n"
            "\n"
            "def test_invalid_cases():\n"
            "    assert is_valid('(]') is False\n"
            "    assert is_valid('([)]') is False\n"
            "    assert is_valid(']') is False\n"
            "\n"
            "\n"
            "def test_empty_string():\n"
            "    assert is_valid('') is True\n"
        ),
    },
]

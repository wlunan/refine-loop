"""
Benchmark 测试集

每个任务是一道「用 Python 实现 / 修复 X」的编码题，评测的客观依据是**预先写好的
ground truth 单元测试**（而非 Critic 的主观评分）：Agent 生成/修复实现代码，评测器
运行这些测试，通过即视为正确。

任务字段：
- name:        任务名（同时是实现模块名）
- description: 任务描述（给 Agent 的 prompt，需明确写入的文件名）
- test_file:   ground truth 测试文件名
- test_code:   ground truth 测试代码（评测器写入 workspace 后运行）
- seed_files:  （可选）预置到 workspace 的初始文件，文件名 -> 内容。
               用于「修复 bug」类任务：先把有缺陷的实现放进工作区，再让 Agent
               读、改、验证，从而拉开 baseline（单次生成）与自愈闭环的差距。

任务难度分布（刻意拉开区分度，避免「全部太简单」导致 baseline 通过率虚高）：
- 简单对照组（baseline 大概率通过）：binary_search
- 中等算法、多边界：merge_intervals
- 修复 bug（baseline 大概率失败、自愈闭环通过）：csv_parser、ip_validator
- 多文件协作：logger（logger.py + formatter.py）
"""

BENCHMARK_VERSION = "2026.09.06.v2"

TASKS = [
    # ------------------------------------------------------------------
    # 简单对照组：单函数经典算法，baseline 大概率一次通过
    # ------------------------------------------------------------------
    {
        "name": "binary_search",
        "description": (
            "实现二分查找函数，写入 binary_search.py 文件。"
            "要求：binary_search(nums, target) 在升序数组 nums 中查找 target，"
            "返回其下标；若不存在返回 -1。需处理空数组、单元素、重复元素与边界情况。"
        ),
        "test_file": "test_binary_search.py",
        "test_code": """\
from binary_search import binary_search


def test_found_middle():
    assert binary_search([1, 2, 3, 4, 5], 3) == 2


def test_found_boundaries():
    assert binary_search([1, 2, 3, 4, 5], 1) == 0
    assert binary_search([1, 2, 3, 4, 5], 5) == 4


def test_not_found():
    assert binary_search([1, 2, 3, 4, 5], 6) == -1


def test_empty_and_single():
    assert binary_search([], 1) == -1
    assert binary_search([7], 7) == 0
    assert binary_search([7], 8) == -1


def test_duplicates():
    idx = binary_search([1, 2, 2, 2, 3], 2)
    assert idx in (1, 2, 3)
""",
    },
    # ------------------------------------------------------------------
    # 中等算法、多边界：区间合并，乱序/包含/相接等多种情况
    # ------------------------------------------------------------------
    {
        "name": "merge_intervals",
        "description": (
            "实现区间合并函数，写入 merge_intervals.py 文件。"
            "要求：merge_intervals(intervals) 接收区间列表（每个区间为 [start, end] "
            "的二元列表），合并所有重叠区间后返回新列表（list of list）。"
            "两个区间若 end >= 下一个 start 则视为重叠需合并（含首尾相接，如 "
            "[1,3] 与 [3,5] 合并为 [1,5]）。需处理：空列表、单区间、乱序输入、"
            "完全包含、部分重叠、互不重叠等边界情况。"
        ),
        "test_file": "test_merge_intervals.py",
        "test_code": """\
from merge_intervals import merge_intervals


def test_empty_and_single():
    assert merge_intervals([]) == []
    assert merge_intervals([[1, 3]]) == [[1, 3]]


def test_no_overlap():
    assert merge_intervals([[1, 2], [3, 4], [5, 6]]) == [[1, 2], [3, 4], [5, 6]]


def test_partial_overlap():
    assert merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]]) == [
        [1, 6],
        [8, 10],
        [15, 18],
    ]


def test_contained():
    assert merge_intervals([[1, 4], [2, 3]]) == [[1, 4]]


def test_unsorted_input():
    assert merge_intervals([[8, 10], [1, 3], [2, 6]]) == [[1, 6], [8, 10]]


def test_touching():
    # end == start 视为重叠，需合并
    assert merge_intervals([[1, 3], [3, 5]]) == [[1, 5]]
""",
    },
    # ------------------------------------------------------------------
    # 修复 bug：预置一个只按逗号切分、不处理引号的 CSV 解析器
    # ------------------------------------------------------------------
    {
        "name": "csv_parser",
        "description": (
            "工作区中已存在 csv_parser.py，实现了 parse_csv(text) 把 CSV 文本解析为"
            "二维列表（每行一个列表，每个字段一个字符串）。当前实现存在 bug，无法"
            "正确处理标准 CSV 的引号语法。请阅读 csv_parser.py 并修复，使其正确支持："
            "① 字段可用双引号包裹，引号内的逗号不是分隔符；② 引号内的换行属于同一"
            "字段，不拆行；③ 双引号内连续两个引号（\"\"）表示一个转义的引号字符；"
            "④ 空字段需保留为空字符串。修复后保存到 csv_parser.py。"
        ),
        "test_file": "test_csv_parser.py",
        "test_code": """\
from csv_parser import parse_csv


def test_simple():
    assert parse_csv("a,b,c\\n1,2,3") == [["a", "b", "c"], ["1", "2", "3"]]


def test_quoted_comma():
    assert parse_csv('name,desc\\n"a,b",x') == [["name", "desc"], ["a,b", "x"]]


def test_escaped_quote():
    # 双引号包裹字段内，"" 表示一个转义的引号字符
    assert parse_csv('"a""b",c') == [['a"b', 'c']]


def test_newline_in_quotes():
    assert parse_csv('a,"line1\\nline2",b') == [["a", "line1\\nline2", "b"]]


def test_empty_field():
    assert parse_csv("a,,c") == [["a", "", "c"]]
""",
        "seed_files": {
            "csv_parser.py": """\
\"\"\"CSV 解析器（存在 bug，待修复）\"\"\"


def parse_csv(text):
    \"\"\"把 CSV 文本解析为二维列表，每行一个列表，每个字段一个字符串。\"\"\"
    lines = text.strip().split("\\n")
    rows = []
    for line in lines:
        rows.append(line.split(","))
    return rows
""",
        },
    },
    # ------------------------------------------------------------------
    # 多文件协作：logger.py + formatter.py，跨文件 import + 级别过滤
    # ------------------------------------------------------------------
    {
        "name": "logger",
        "description": (
            "实现一个带级别过滤的日志器，需创建两个文件并互相引用："
            "① formatter.py：提供 format_message(level, message) 函数，返回形如 "
            "'[LEVEL] message' 的字符串（LEVEL 需转大写）；"
            "② logger.py：提供 Logger 类，构造函数 Logger(level='INFO')，提供 "
            "log(level, message) 方法（级别低于阈值时丢弃该条消息），以及 "
            "debug/info/warning/error 便捷方法；每条被记录的消息以格式化后的字符串"
            "追加到实例属性 messages 列表。级别顺序：DEBUG < INFO < WARNING < ERROR；"
            "level 大小写不敏感。"
        ),
        "test_file": "test_logger.py",
        "test_code": """\
from logger import Logger
from formatter import format_message


def test_format_message():
    assert format_message("INFO", "hello") == "[INFO] hello"
    assert format_message("ERROR", "boom") == "[ERROR] boom"


def test_level_filtering():
    log = Logger(level="INFO")
    log.debug("d")
    log.info("i")
    log.warning("w")
    log.error("e")
    assert log.messages == ["[INFO] i", "[WARNING] w", "[ERROR] e"]


def test_default_level():
    log = Logger()
    log.debug("d")
    log.info("i")
    assert log.messages == ["[INFO] i"]


def test_case_insensitive_level():
    log = Logger(level="info")
    log.info("i")
    assert log.messages == ["[INFO] i"]


def test_error_only():
    log = Logger(level="ERROR")
    log.warning("w")
    log.error("e")
    assert log.messages == ["[ERROR] e"]
""",
    },
    # ------------------------------------------------------------------
    # 修复 bug：预置一个用 int() 校验、漏掉前导零与空白处理的 IPv4 校验器
    # ------------------------------------------------------------------
    {
        "name": "ip_validator",
        "description": (
            "工作区中已存在 ip_validator.py，实现了 is_valid_ipv4(s) 判断字符串是否"
            "为合法 IPv4 地址。当前实现存在边界 bug。请阅读并修复，使其满足："
            "IPv4 由 4 个 0-255 的十进制数字组成，用点分隔；不允许前导零（如 "
            "'01.2.3.4'、'192.168.001.1' 无效）；不允许前后空白字符；不允许负数；"
            "含非数字字符或段数不为 4 均无效。修复后保存到 ip_validator.py。"
        ),
        "test_file": "test_ip_validator.py",
        "test_code": """\
from ip_validator import is_valid_ipv4


def test_valid():
    assert is_valid_ipv4("192.168.1.1") is True
    assert is_valid_ipv4("0.0.0.0") is True
    assert is_valid_ipv4("255.255.255.255") is True


def test_out_of_range():
    assert is_valid_ipv4("256.1.1.1") is False
    assert is_valid_ipv4("1.1.1.256") is False


def test_wrong_segment_count():
    assert is_valid_ipv4("1.2.3") is False
    assert is_valid_ipv4("1.2.3.4.5") is False


def test_non_numeric():
    assert is_valid_ipv4("1.2.3.a") is False


def test_leading_zeros():
    assert is_valid_ipv4("01.2.3.4") is False
    assert is_valid_ipv4("192.168.001.1") is False


def test_negative():
    assert is_valid_ipv4("-1.2.3.4") is False


def test_whitespace():
    assert is_valid_ipv4(" 1.2.3.4") is False
    assert is_valid_ipv4("1.2.3.4 ") is False
""",
        "seed_files": {
            "ip_validator.py": """\
\"\"\"IPv4 校验（存在 bug，待修复）\"\"\"


def is_valid_ipv4(s):
    \"\"\"判断字符串是否为合法 IPv4 地址。\"\"\"
    parts = s.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        try:
            num = int(p)
        except ValueError:
            return False
        if num < 0 or num > 255:
            return False
    return True
""",
        },
    },
]

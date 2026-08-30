# ADR-0003: Critic 结构化输出的防御性解析

## 状态
已接受

## 背景
LLM（尤其弱模型，如小米 mimo）输出 JSON 经常不规范：字段缺失、类型错误、夹带解释文字。直接 `CritiqueResult(**data)` 会因 Pydantic 严格校验频繁失败，导致「解析降级」。

## 决策
采用「三级降级解析 + 类型容错」链路：

```
LLM 原始回复
  ├─ ① parser.parse() 直接按 Pydantic 解析         → 成功返回
  ├─ ② _extract_json() 提取 JSON（```json 块 / 首个{到末个}）
  │      → json.loads → _coerce_critique() 类型容错   → 成功返回
  └─ ③ 降级兜底：score=50, acceptable=False，带回原始片段
```

配套两个关键点：
- 把 `PydanticOutputParser.get_format_instructions()` 的 JSON Schema 注入 Prompt（否则弱模型不知道字段结构）
- `_coerce_critique` 做类型容错：`"85"` 字符串转 int、字符串转列表、字符串布尔转 bool，并处理 `acceptable` 与 `score` 的一致性冲突（`acceptable=True` 时 `score` 不得低于 60）

## 理由
- 永远不信任模型输出一定规范，层层设防、永不崩溃
- 降级结果仍带回原始片段，便于定位问题（而非静默失败）

## 后果
- 弱模型可稳定接入（配合模型分级），但「解析降级」仍会降低审查质量 → 后续可改用 JSON mode / function calling 根治（见 ARCHITECTURE 已知方向）

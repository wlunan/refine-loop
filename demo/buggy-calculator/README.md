# Buggy Calculator Demo

这是 RefineLoop 的固定演示项目。初始实现故意包含折扣计算和输入校验错误。

在 RefineLoop 中选择准备脚本输出的工作区，然后使用以下任务：

> 修复 `src/cart.py` 的价格计算与输入校验问题，使全部测试通过。保持 `calculate_total` 的函数签名不变，不要修改测试。

预期流程：pytest 首轮失败 → 失败证据回注 → Agent 修复 → pytest 通过 → 审阅并应用 diff。

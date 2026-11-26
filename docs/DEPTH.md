# 可复核的模型和处置边界

分类 AI/ML / 传统ML。

## 功能模块

| 模块 | 业务步骤 | 输出 | 核心实现 | 独立契约与边界测试 |
|---|---|---|---|---|
| M1 | 领用流水 | UsageTicket处理证据 | `src/clinicstock/usage_receipts/contracts.py` `src/clinicstock/usage_receipts/algorithm.py` `src/clinicstock/usage_receipts/service.py` `src/clinicstock/usage_receipts/movement_ledger.py` `src/clinicstock/usage_receipts/point_in_time.py` | `tests/test_usage_receipts.py` `tests/test_movement_ledger.py` `tests/test_point_in_time.py` |
| M2 | 可售修复 | DailyShelf处理证据 | `src/clinicstock/outage_today/contracts.py` `src/clinicstock/outage_today/algorithm.py` `src/clinicstock/outage_today/service.py` `src/clinicstock/outage_today/stockout_review.py` | `tests/test_outage_today.py` `tests/test_stockout_review.py` |
| M3 | 用量建模 | DemandDay处理证据 | `src/clinicstock/demand_smoothing/contracts.py` `src/clinicstock/demand_smoothing/algorithm.py` `src/clinicstock/demand_smoothing/service.py` | `tests/test_demand_smoothing.py` |
| M4 | 残差区间 | ValidationDemand处理证据 | `src/clinicstock/reorder_bands/contracts.py` `src/clinicstock/reorder_bands/algorithm.py` `src/clinicstock/reorder_bands/service.py` `src/clinicstock/reorder_bands/window_replay.py` `src/clinicstock/reorder_bands/weekly_replay.py` | `tests/test_reorder_bands.py` `tests/test_coverage_replay.py` `tests/test_weekly_replay.py` |
| M5 | 整箱分配 | PurchaseRequest处理证据 | `src/clinicstock/carton_budget/contracts.py` `src/clinicstock/carton_budget/algorithm.py` `src/clinicstock/carton_budget/service.py` `src/clinicstock/carton_budget/purchase_portfolio.py` | `tests/test_carton_budget.py` `tests/test_purchase_portfolio.py` `tests/test_emergency_and_tiers.py` |
| M6 | 消耗复盘 | ConsumptionClose处理证据 | `src/clinicstock/consumption_review/contracts.py` `src/clinicstock/consumption_review/algorithm.py` `src/clinicstock/consumption_review/service.py` `src/clinicstock/consumption_review/holdout_comparison.py` | `tests/test_consumption_review.py` `tests/test_holdout_comparison.py` |

## 边界登记

| 陷阱 | 业务输入 | 处理位置 | 验证锚点 |
|---|---|---|---|
| TRAP-14 | 同一凭证同修订的领用和退回冲突单独留证 | `src/clinicstock/usage_receipts/algorithm.py` | `tests/test_usage_receipts.py::test_returns_and_issues_cannot_share_a_revision` |
| TRAP-19 | 优先保障紧缺目录，输入反转后分配不变 | `src/clinicstock/carton_budget/algorithm.py` | `tests/test_carton_budget.py::test_critical_supply_receives_tie_break_even_if_later_identifier` |
| TRAP-26 | 晚到旧记账修订不会覆盖新流水 | `src/clinicstock/usage_receipts/algorithm.py` | `tests/test_usage_receipts.py::test_revision_supersedes_original_amount_without_order_dependence` |
| TRAP-33 | 验证窗口非整除尾段和中间断供不计入完整训练窗口 | `src/clinicstock/reorder_bands/algorithm.py` | `tests/test_reorder_bands.py::test_nonoverlap_validation_blocks_drop_incomplete_intervals` |
| TRAP-42 | 未来正常用量不能修复早期被截尾需求 | `src/clinicstock/outage_today/algorithm.py` | `tests/test_outage_today.py::test_later_day_never_corrects_earlier_censored_demand` |
| TRAP-43 | 没有已核完整窗口时覆盖率留空 | `src/clinicstock/reorder_bands/algorithm.py` | `tests/test_reorder_bands.py::test_group_without_enough_closed_windows_leaves_buffer_unknown` |
| TRAP-53 | 另一个诊室的预测批次不会改变原诊室预测 | `src/clinicstock/demand_smoothing/algorithm.py` | `tests/test_demand_smoothing.py::test_different_store_does_not_change_forecast` |
| TRAP-54 | 模型平滑系数变化时拟合标识改变 | `src/clinicstock/demand_smoothing/algorithm.py` | `tests/test_demand_smoothing.py::test_different_smoothing_parameter_invalidates_fingerprint` |
| TRAP-61 | 迟到修订只更正结算用量，周初预测仍按当时可见流水回放 | `src/clinicstock/usage_receipts/point_in_time.py` `src/clinicstock/reorder_bands/weekly_replay.py` | `tests/test_weekly_replay.py::test_late_revision_keeps_week_start_forecast_but_updates_settled_usage` |
| TRAP-62 | 含断供日的周不进入安全库存核量，但断供回补量仍参与后续训练 | `src/clinicstock/reorder_bands/weekly_replay.py` | `tests/test_weekly_replay.py::test_week_with_outage_day_is_not_a_complete_backtest_week` |
| TRAP-63 | 完整回测周不足时关键耗材仍给应急整箱、一般耗材留人工 | `src/clinicstock/carton_budget/algorithm.py` | `tests/test_emergency_and_tiers.py::test_critical_unvalidated_item_gets_emergency_cases_for_forecast_gap` |
| TRAP-64 | 预算不足时关键预计缺口先于一般缺口、再先于经验证安全库存 | `src/clinicstock/carton_budget/algorithm.py` `src/clinicstock/carton_budget/purchase_portfolio.py` | `tests/test_emergency_and_tiers.py::test_budget_funds_critical_gap_before_standard_gap` |

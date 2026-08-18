# 分析报告：模块化应用壳与视觉系统基础

**功能**：[spec.md](./spec.md)
**分析日期**：2026-08-11
**产物就绪度**：READY
**执行环境**：PARTIAL
**模式**：工作流产物审查；未修改业务源代码

## 决策摘要

| 分类 | 数量 | 下一负责人 |
|------|------|------------|
| Agent 自动修复 | 0 | 无 |
| 用户决策 | 0 | 无 |
| 外部阻塞 | 0 | 无 |
| 已接受风险 | 2 | 实施阶段记录与验证 |

## 发现

### A001 — 前端暂无自动化交互测试框架

- **严重度**：MEDIUM
- **负责人**：AGENT
- **解决类型**：ACCEPTED_RISK
- **状态**：ACCEPTED
- **证据**：
  - `frontend/package.json` — 只有 dev/build/preview 脚本，没有 unit 或 browser test 工具。
  - `specs/001-modular-shell/test-cases.md` — 路由历史、响应式和键盘行为由手工用例覆盖。
- **影响**：Vue Router 迁移中的历史状态、焦点和响应式回归不能仅靠 build 捕获。
- **解决**：本次以 production build、结构检查和真实浏览器手工检查作为门禁；前端测试框架作为后续工程质量任务，不在壳层重构中叠加。
- **解决记录**：用户已批准兼容性优先的壳层范围；计划和测试用例已明确手工门禁。

### A002 — 真实 DataFlow 端到端执行不是默认测试环境

- **严重度**：LOW
- **负责人**：AGENT
- **解决类型**：ACCEPTED_RISK
- **状态**：ACCEPTED
- **证据**：
  - `tests/test_end_to_end.py` — 真实集成由 `DATAFORGE_TEST_DATAFLOW=1` 显式启用。
  - `src/dataforge/dataflow_studio.py` — 当 DataFlow 不可用时支持降级挂载。
- **影响**：默认回归可以验证降级和接口，但不能证明所有本地 DataFlow 算子运行时均可执行。
- **解决**：本次不改变 DataFlow 执行逻辑，以现有 opt-in 集成和 Studio 挂载测试为边界；模块开发阶段再进行真实样本验收。
- **解决记录**：已在 plan/test-cases 中分离默认环境和真实 DataFlow 环境。

## 覆盖摘要

- FR-001/FR-002 由模块注册表、后端路由分组和 T002/T004/T006 覆盖。
- FR-003/FR-004 由 T002/T003/T010、TC-001 至 TC-004/TC-012 覆盖。
- FR-005/FR-006 由 T004-T009、TC-005 至 TC-010 覆盖。
- FR-007 由模块注册表可用状态、T004/T009 和 TC-011 覆盖。
- 所有需求来源均在 intake/spec 中登记并映射到需求或测试。
- 后端与前端的依赖顺序明确；共享契约完成后并行标记安全，最终在 T010 汇合。

## 执行环境摘要

- **已验证**：Python 3.11/uv/root pytest、Node/npm、DataForge frontend build、vendored DataFlow frontend build 在 2026-08-11 当前工作区成功运行。
- **未验证/缺失**：尚未安装本次新增的 `vue-router`；尚未在真实浏览器执行新版 UI；真实 DataFlow E2E 默认未启用。
- **解释**：这些是实施后验证项，不影响工作流产物就绪度，因此环境状态为 PARTIAL，产物仍为 READY。

## 解决历史

| 时间 | 发现 | 操作 | 文件/决策 |
|------|------|------|-----------|
| 2026-08-11 | A001 | 接受本次不引入测试框架，以 build + 浏览器门禁补足 | `plan.md`、`test-cases.md` |
| 2026-08-11 | A002 | 保留 DataFlow opt-in E2E 边界 | `plan.md`、`test-cases.md` |

## 下一步

执行 `$devora-implement`，按 `tasks.md` 实施并逐项记录验证结果。

# 任务：模块化应用壳与视觉系统基础

**输入**：`spec.md`、`plan.md`、`test-cases.md`

## 阶段 1：共享契约与前置条件

- [X] T001 [Workspace] 在 `specs/001-modular-shell/` 固化模块注册、兼容路径和设计 Token 约束 — Depends on: None — Implementation: DONE — Validation: PASSED — Validate: 规格、计划和测试范围一致
- [X] T002 [Backend] 在 `src/dataforge/api/` 建立模块路由并将 `src/dataforge/web.py` 收敛为组合根 — Depends on: T001 — Implementation: DONE — Validation: PASSED — Validate: root pytest 15 passed
- [X] T003 [Backend] 在 `tests/test_web.py` 增加关键模块路径合同检查 — Depends on: T002 — Implementation: DONE — Validation: PASSED — Validate: 公开路径合同和 Studio 挂载测试通过

## 阶段 2：用户故事 1——可导航的模块化应用

**目标**：现有七个页面通过 Vue Router 和模块注册表访问，导航、刷新与历史行为保持可用。
**独立测试**：生产构建成功，模块注册表只暴露已实现页面，核心路由可直接解析。

- [X] T004 [Frontend] 引入 Vue Router 与五模块注册契约 — Depends on: T001 — Implementation: DONE — Validation: PASSED — Validate: module registry contract 和 build 通过
- [X] T005 [Frontend] 迁移跨页状态到 `useDataForgeWorkspace.js` — Depends on: T004 — Implementation: DONE — Validation: PASSED — Validate: API 路径不变且 build 通过
- [X] T006 [Frontend] 将七个页面拆到 `frontend/src/modules/**/pages/*.vue` — Depends on: T005 — Implementation: DONE — Validation: PASSED — Validate: 七个 lazy chunks 构建成功
- [X] T007 [Frontend] 新建 `AppShell.vue` 并精简根 `App.vue` — Depends on: T006 — Implementation: DONE — Validation: PASSED — Validate: Hash 路由和模块导航浏览器检查通过

## 阶段 3：用户故事 2——统一视觉系统

**目标**：现有页面采用专业企业数据工作台风格，具备一致状态、响应式、焦点和减少动效支持。
**独立测试**：四个目标宽度可用，键盘焦点可见，状态不只依赖颜色。

- [X] T008 [Frontend] 建立三层 Token、base 和 app 样式入口 — Depends on: T004 — Implementation: DONE — Validation: PASSED — Validate: production build 通过
- [ ] T009 [Frontend] 应用 Precision Data Workbench 视觉和响应式基础 — Depends on: T007, T008 — Implementation: DONE — Validation: PENDING — Validate: 375px/1280px 已通过；768/1024/1440 与完整键盘巡检待正式 review

## 阶段 4：跨项目集成

- [ ] T010 [Workspace] 联调 FastAPI、frontend dist、`/studio` 与 SPA fallback — Depends on: T003, T009 — Implementation: DONE — Validation: PENDING — Validate: 自动化与浏览器集成已通过，等待 T009 完整视觉门禁
- [ ] T011 [Workspace] 更新项目上下文和功能摘要 — Depends on: T010 — Implementation: DONE — Validation: PENDING — Validate: 等待上游 T009/T010 完成

## 阶段 5：最终验证

- [ ] T012 [Workspace] 运行 root pytest、DataForge frontend build、结构检查和手工 UI 验收 — Depends on: T001-T011 — Implementation: N/A — Validation: PENDING — Validate: TC-001 至 TC-012 满足退出标准

## 状态摘要

| 指标 | 数量 |
|------|------|
| 实施完成 | 11 |
| 验证通过 | 8 |
| 完全完成 | 8 |
| 阻塞 | 0 |

## 依赖摘要

关键路径为 T001 → T002/T004 → T005 → T006 → T007 → T009 → T010 → T011 → T012。后端 T002-T003 与前端 T004-T009 在共享契约完成后可独立推进，最终在 T010 汇合。

## 并行机会

- T002 与 T004 在 T001 完成后文件独立。
- T003 可与 T005-T009 并行，但必须等待 T002。
- T008 在 T004 完成后可与 T005-T007 并行，T009 汇合结构和 Token。

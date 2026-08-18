# 测试用例：模块化应用壳与视觉系统基础

**规格**：[spec.md](./spec.md)
**计划**：[plan.md](./plan.md)
**状态**：READY

## 覆盖矩阵

| 测试 ID | 需求/来源 | 层级 | 场景 | 预期结果 | 自动化 | 状态 |
|---------|-----------|------|------|----------|--------|------|
| TC-001 | FR-003 / SRC-004 | integration | 运行现有 root pytest | 所有现有接口和生命周期测试通过 | AUTO | PLANNED |
| TC-002 | FR-003 / SRC-004 | contract | 检查关键 `/api/*` 路径 | 文档、处理、资产和知识接口路径完整 | AUTO | PLANNED |
| TC-003 | FR-004 / SRC-003 | e2e | 上传文本并运行 native pipeline | 生成可预览、可下载、可溯源资产 | AUTO | PLANNED |
| TC-004 | FR-004 / SRC-003 | integration | 创建知识任务并查看知识库 | 使用默认已验证流程并完成入库 | AUTO | PLANNED |
| TC-005 | FR-006 / SRC-004 | build | 构建 DataForge frontend | Vite production build 成功 | AUTO | PLANNED |
| TC-006 | FR-001 / SRC-001 | contract | 检查模块注册表 | 五个一级边界存在，只有已实现页面进入导航 | AUTO | PLANNED |
| TC-007 | FR-006 / SRC-005 | manual/e2e | 导航、刷新、前进和返回 | 页面、URL 和来源路径一致 | MANUAL | PLANNED |
| TC-008 | FR-005 / SRC-005 | manual | 检查四个响应式宽度 | 无全局横向滚动，层级与主操作清晰 | MANUAL | PLANNED |
| TC-009 | FR-005 / SRC-005 | manual | 键盘和焦点检查 | 核心操作可达且焦点可见 | MANUAL | PLANNED |
| TC-010 | FR-005 / SRC-005 | manual | 状态与 reduced-motion 检查 | 状态含文字/形状，减少动效设置被尊重 | MANUAL | PLANNED |
| TC-011 | FR-007 / SRC-003 | manual | 查看所有导航和按钮 | 未实现索引/AI 应用不呈现可执行入口 | MANUAL | PLANNED |
| TC-012 | FR-004 / SRC-004 | integration | DataFlow 不可用时创建应用 | SPA 与状态 API 可用，Studio 显示降级 | AUTO/MANUAL | PLANNED |

## 功能与验收用例

- 业务用户可以进入工作台、文档、处理任务和知识资产页面，并完成现有主流程。
- 技术人员可以进入知识类型、标准流程和 DataFlow Studio 页面。
- 直接访问等价 Hash 路由、刷新和浏览器历史导航均有效。
- 模块注册表明确区分已实现和未来模块。

## 失败与恢复用例

- API 请求失败时页面展示包含恢复方向的错误，不留下永久 busy 状态。
- DataFlow Studio 不可用时页面说明原因，业务模块仍可操作。
- 上传或任务创建校验失败时，表单数据和返回路径不被意外清空。

## 安全与权限用例

- 当前无身份系统；确认重构不错误声明已具备权限隔离。
- 前端错误和状态区域不新增密钥、完整内部异常栈或敏感配置展示。
- 文件名继续经过 `Path(...).name` 归一化，上传路径行为保持现有测试覆盖。

## 边界、并发与兼容性用例

- 375px 小屏、1440px 大屏均可使用。
- 长文件名、空列表、长知识记录和较宽表格不会破坏整个页面布局。
- 后台任务 pending/running/completed/failed 状态在页面一致表达。
- 原 `/api/*` 路径、响应和 `/studio` 挂载保持向后兼容。

## 跨项目与端到端用例

- DataForge 与相邻 DataFlow 存在时，Studio 状态和 iframe 路径保持正确。
- DataFlow 不存在时，native 流程和业务 SPA 仍可运行。
- 业务前端构建产物继续由 FastAPI SPA fallback 提供。

## 手工产品/设计检查

- 视觉语言符合企业数据工作台，而不是营销站或通用 AI 渐变页面。
- 一个页面只有一个清晰主操作，次要操作视觉降级。
- 业务区和开发区具有共同设计语言，同时技术区允许更高信息密度。
- 正常、选中、悬停、聚焦、禁用、加载、成功、等待和失败状态可区分。
- 触控目标至少 44px，文本对比度符合 WCAG AA 的合理人工检查。

## 环境与测试数据

- Python 3.11/3.12、uv、Node.js、npm。
- root pytest 的临时目录 fixture；不依赖现有 `.dataforge` 用户数据。
- 响应式检查使用现代 Chromium；真实 DataFlow 检查需要相邻 `/Users/mac/ai/DataFlow`。

## 退出标准

- TC-001 至 TC-006 和 TC-012 的可自动化部分通过。
- 核心现有业务链路无回归。
- TC-007 至 TC-011 完成手工检查且无阻断问题。
- 前端生产构建成功，根测试无新增失败。

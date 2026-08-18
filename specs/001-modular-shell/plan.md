# 实施计划：模块化应用壳与视觉系统基础

**日期**：2026-08-11 | **规格**：[spec.md](./spec.md)
**测试用例**：[test-cases.md](./test-cases.md)

## 摘要

采用兼容性优先的渐进式重构。后端保留 FastAPI 单一组合根和现有 service/storage，实现 documents、processing、assets 等模块路由工厂；前端保留 Vue 3/Vite，使用 Vue Router 的 Hash History 保持现有 URL 可刷新性，拆出应用壳、模块页面、共享状态和三层设计 Token。索引与 AI 应用只进入模块注册模型，不显示未实现操作。

## 依据

### 复用的现有组件

- `src/dataforge/application.py`：处理生命周期与资产发布，保持原行为。
- `src/dataforge/ingestion.py`：文档上传后的来源/版本服务。
- `src/dataforge/knowledge.py`：知识任务、验证、知识库和溯源服务。
- `src/dataforge/dataflow_studio.py`：DataFlow Studio 挂载与桥接。
- `src/dataforge/database.py`：本次不改 Schema，继续作为持久化实现。
- `frontend/src/api.js`：保留现有 HTTP 契约，后续按模块导出客户端。
- `frontend/src/App.vue`：复用现有业务行为和页面文案，拆分而非重写。
- `frontend/src/styles.css`：保留有效布局规则，迁移到 Token 驱动的样式入口。

### 已验证约束

- `/api/*`、`/api/v1/*`、`/studio` 和 SPA fallback 必须保持兼容。
- DataFlow Studio 在核心项目不可用时允许降级，不能阻止业务 SPA 加载。
- 现有根测试通过；真实 DataFlow 集成为 opt-in。
- constitution 是占位模板，没有额外可执行规则；以规格、README 和当前测试作为本次门禁。
- 未实现模块不得显示为可点击功能。

## 技术上下文

| 项目 | 类型 | 语言/框架 | 测试 | 本功能职责 |
|------|------|-----------|------|------------|
| DataForge backend | API/CLI | Python 3.11/3.12、FastAPI、SQLite | root pytest | 模块路由、组合根、兼容 API |
| DataForge frontend | SPA | Vue 3、Vite | production build + 手工 UI 检查 | 模块页面、路由、应用壳、设计系统 |
| DataFlow Studio | vendored SPA/API | Vue/FastAPI | 现有挂载测试、独立 build | 保持嵌入契约，不修改业务 |

## Constitution 检查

- **PASS（替代门禁）**：constitution 尚未定义真实原则；规格明确保持接口兼容、不建设未实现业务、运行现有测试。
- **PASS（范围）**：不修改生产数据模型、权限或外部 DataFlow 所有权。
- **PASS（质量）**：计划包含自动化、构建、响应式、键盘和视觉检查。

## 按项目的变更设计

### DataForge 后端

**当前结构**：`src/dataforge/web.py` 在单一函数中声明所有请求模型、工具函数和 API。

**计划变更**：

- 新建 `src/dataforge/api/` 作为 API 组合层。
- 新建公共请求模型和辅助函数，避免模块间从 `web.py` 反向导入。
- 将路由按职责拆为：
  - `dashboard.py`：健康状态和工作台聚合；
  - `documents.py`：来源上传、来源列表与版本；
  - `processing.py`：DataFlow Studio、Pipeline、知识类型、标准流程、知识任务和 run；
  - `assets.py`：知识库、知识记录溯源、旧资产预览/下载兼容接口。
- `web.py` 只负责实例化 DataForge/KnowledgeService、挂载 Studio、注册路由、异常处理、CORS 和 SPA 静态资源。
- 不移动 service 和数据库实现，不修改响应结构。

**验证**：

- `uv run --with pytest --extra dataflow --extra web --extra studio pytest -q`

### DataForge 前端

**当前结构**：`frontend/src/App.vue` 包含全部页面、状态和手写路由；`styles.css` 是单一全局文件。

**计划变更**：

- 增加 `vue-router`，使用 `createWebHashHistory` 兼容现有 Hash URL 和静态托管。
- 新建 `app/moduleRegistry.js`，登记 documents、processing、assets 以及尚未开放的 indexing/applications 边界；导航只渲染已实现页面。
- 新建 `app/router.js` 和 `layouts/AppShell.vue`，让根 `App.vue` 只承载 RouterView。
- 新建共享 `composables/useDataForgeWorkspace.js`，集中现有跨页面状态、API 刷新和操作；这是过渡性应用 store，避免拆分期间丢失行为，不引入另一套业务状态语义。
- 将七个现有页面拆到：
  - `modules/dashboard/pages/OverviewPage.vue`
  - `modules/documents/pages/DocumentsPage.vue`
  - `modules/processing/pages/JobsPage.vue`
  - `modules/processing/pages/KnowledgeTypesPage.vue`
  - `modules/processing/pages/StandardPipelinesPage.vue`
  - `modules/processing/pages/StudioPage.vue`
  - `modules/assets/pages/AssetsPage.vue`
- 新建共享 UI 组件，至少覆盖状态徽标、页面头部/空状态或图标导航中实际重复的部分；不为形式拆出一次性组件。
- API 仍由同一 request 基础函数调用，按模块导出语义分组，同时保留现有调用契约。
- 新建设计文件：
  - `styles/tokens.css`：primitive、semantic、component Token；
  - `styles/base.css`：重置、字体、焦点、reduced-motion；
  - `styles/app.css`：应用布局与现有页面样式。
- 视觉采用“Precision Data Workbench”：中性浅色表面、深蓝结构导航、蓝色主操作、绿色成功、琥珀等待、红色失败、低强度阴影与 150–250ms 状态过渡。
- 中文正文保持系统中文字体；等宽字体只用于 ID、结构字段和技术内容，不使用 Fira Code 作为中文标题字体。

**验证**：

- `cd frontend && npm run build`
- 启动本地 API 后检查核心路由、375/768/1024/1440 宽度、键盘焦点和 reduced-motion。

## 跨项目契约与顺序

1. 先建立后端路由模块并运行测试，保证 API 基线稳定。
2. 再建立前端 router/module registry/store，保持 API client 路径不变。
3. 按页面拆模板并挂到路由，最后替换根 App。
4. 应用 Token 和新版外壳样式；不修改 `/studio` iframe 内部样式。
5. 构建前端后，由 FastAPI 继续服务 `frontend/dist`。

DataFlow 发现方式、`/api/v1` 路由和 `/studio` 挂载顺序不变。

## 数据与迁移

本次无数据库 Schema 或业务数据迁移。回滚可以恢复旧路由声明和旧前端 dist；`.dataforge` 运行数据不受影响。

新增的前端依赖只限 `vue-router`。暂不引入 Pinia、Tailwind 或组件库，避免在壳层重构时叠加大规模技术迁移；设计 Token 使用原生 CSS 变量。

## 风险与缓解

| 风险 | 证据 | 缓解 |
|------|------|------|
| 页面拆分造成向导/返回状态丢失 | `frontend/src/App.vue` 手写 routeDepth 和 returnLabel | 使用 Vue Router history state/route meta，并在共享 workspace store 中保存跨页状态 |
| API 路由注册顺序或依赖变化 | `src/dataforge/web.py` 通过闭包共享对象 | 所有路由工厂显式接收 DataForge、KnowledgeService、Studio、Settings；`web.py` 保持唯一组合根 |
| 风格重做降低信息密度 | 当前页面已有多列表、表格、对照区 | Token 先行，保留页面信息架构；只调整层级、间距、状态和导航 |
| Hash 兼容回归 | 现有 URL 是 `#/workspace/page` | Vue Router 复用等价路径并增加重定向/别名 |
| Studio 不可用影响初始化 | `mount_dataflow_studio` 支持降级 | 保留挂载顺序和状态 API，前端显示明确降级状态 |

## 交付验证

- 自动化：根 pytest 覆盖文档 → run → 资产、知识生产、接口错误和 Studio 挂载。
- 合同：比较重构前后 OpenAPI 关键 `/api/*` 路径集合；现有前端 API 字符串保持不变。
- 构建：DataForge Vue production build 必须成功。
- E2E/手工：导航、刷新、返回、文档上传、任务创建、知识库查看、溯源、技术区和 Studio 降级。
- 视觉：四个视口、键盘焦点、触控目标、状态非颜色表达、无全局横向滚动、reduced-motion。

## 文档和知识影响

- 更新 `specs/001-modular-shell/` 的规格、计划、任务、测试和总结。
- 更新 `.devora/memory/project-context.md` 中前端结构和后端路由边界。
- 如用户可见运行方式或项目结构变化，更新 `README.md`；本次不改变命令。

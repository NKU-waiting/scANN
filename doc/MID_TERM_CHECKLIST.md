# 中期检查完成清单

本文档说明中期检查前需要在当前代码框架下完成的功能、涉及文件以及验收方式。中期目标不是完成完整结项系统，而是保证“单细胞数据读取 → 向量化 → ANN 索引构建 → Top-K 相似细胞检索 → Web 展示”这条主链路可以稳定演示。

## 1. 中期检查目标

中期检查至少需要完成以下内容：

- 单细胞数据读取。
- 数据向量化表示。
- ANN 索引构建。
- 相似细胞检索。
- 至少实现一种 ANN 算法或接入一种 ANN 检索库。
- 支持 Top-K 相似细胞搜索。
- 返回对应细胞信息。
- 提供可运行的 Web 页面演示。

当前项目技术框架为：

- 后端：`backend/`，Flask REST API。
- 前端：`frontend/`，Vue3 + Vite。
- 检索核心：`backend/app/services/index/`，NumPy Flat 与 FAISS 索引。
- 数据入口：`backend/app/services/data_loader.py`。

## 2. 完整中期检查 Checklist

优先级定义：

- `P0`：中期必须完成的最小实现。缺少任意关键项都会影响中期展示是否成立。
- `P1`：建议完成的加分项。用于提升展示完整度、技术说服力和评分上限。
- `P2`：中期可以不实现的内容。可明确说明为结项阶段继续完善。

### 2.1 P0：必须完成的最小实现

| 完成 | 检查项 | 当前状态 | 涉及文件 | 验收方式 |
| --- | --- | --- | --- | --- |
| [x] | 后端服务可以启动 | 有 Flask 应用工厂和入口 | `backend/run.py`、`backend/app/__init__.py`、`backend/requirements.txt`、`README.md` | 启动后访问 `/api/health` 返回 `200` 和 `status=ok` |
| [x] | 前端服务可以启动并能代理后端 API | 有 Vue3 + Vite 页面和代理配置 | `frontend/package.json`、`frontend/vite.config.js`、`frontend/src/App.vue` | 前端页面能正常打开，并能获取 `/api/index/status` |
| [x] | demo 单细胞数据能自动初始化 | 已有 `make_demo_dataset` | `backend/app/services/data_loader.py`、`backend/app/services/search.py` | 首次访问 `/api/index/status` 后返回数据集名称、细胞数、维度 |
| [x] | 向量数据结构正确 | 已有 `CellDataset` | `backend/app/services/data_loader.py` | 数据向量为二维 `float32`，形状为 `n_cells × dim` |
| [x] | 至少有一个精确检索基线 | 已有 NumPy Flat | `backend/app/services/index/flat_index.py`、`backend/app/services/index/__init__.py` | `index_type=flat` 能构建并查询 |
| [x] | 至少有一个 ANN 索引可用 | 已有 FAISS IVF/HNSW/PQ 实现 | `backend/app/services/index/faiss_index.py`、`backend/app/services/index/__init__.py`、`backend/requirements.txt` | `index_type=hnsw` 或 `index_type=ivf` 能构建并查询 |
| [x] | 索引构建 API 可用 | 已有 `/api/index/build` | `backend/app/api/index.py`、`backend/app/services/search.py` | POST `/api/index/build` 返回当前索引状态 |
| [x] | 索引状态 API 可用 | 已有 `/api/index/status` | `backend/app/api/index.py`、`backend/app/services/search.py` | GET `/api/index/status` 返回 `dataset/n_cells/dim/index/metric/ready` |
| [x] | 按细胞编号 Top-K 查询可用 | 已有 `/api/search` 与 `search_by_cell` | `backend/app/api/search.py`、`backend/app/services/search.py` | POST `/api/search` 传 `cell_id/top_k/index_type/metric` 返回 Top-K |
| [x] | 查询结果包含细胞信息 | 已有基础字段 | `backend/app/services/search.py` | 每条结果包含 `cell_id/cell_name/distance`，有元信息时包含 `cell_type` |
| [x] | 查询耗时能返回并展示 | 后端已有 `query_ms`，前端已有展示 | `backend/app/services/search.py`、`frontend/src/App.vue` | 查询后页面显示查询耗时 |
| [x] | 前端能完成一次完整查询 | 已有单页查询表单 | `frontend/src/App.vue`、`frontend/src/style.css` | 页面输入 `cell_id/top_k/index_type/metric` 后展示结果表格 |
| [x] | 参数错误有明确提示 | 当前部分异常已返回 400 | `backend/app/api/search.py`、`backend/app/services/search.py`、`frontend/src/App.vue` | 非法 `cell_id`、缺少查询对象、向量维度错误时页面能显示错误 |
| [x] | README 有可复现启动和演示步骤 | 已有快速开始，但需与实际实现保持一致 | `README.md` | 按 README 能启动后端、启动前端、完成一次 Top-K 查询 |
| [x] | Git 提交记录可体现开发过程 | 本地已有提交记录 | Git 仓库 | 中期提交前将代码推送到 GitHub，并保留清晰提交记录 |
| [x] | 中期现场演示流程准备完成 | 文档已有建议流程 | `doc/MID_TERM_CHECKLIST.md`、可选 `README.md` | 能在 5-8 分钟内演示启动、建索引、查询和结果展示 |

### 2.2 P1：建议完成的加分项

| 完成 | 检查项 | 当前状态 | 涉及文件 | 验收方式 |
| --- | --- | --- | --- | --- |
| [x] | 接通真实 `.h5ad` 数据加载 API | 已接通 `load_h5ad` 与数据集切换/索引重建 | `backend/app/services/data_loader.py`、`backend/app/api/datasets.py`、`backend/app/services/search.py` | POST `/api/datasets/load` 传数据路径后能加载数据并继续查询 |
| [x] | `.h5ad` 读取有基础校验 | 已校验空数据、非二维、零维度和非法数值 | `backend/app/services/data_loader.py` | 对空数据、非二维数据、维度异常给出明确错误 |
| [x] | 前端支持查询向量输入 | 已增加向量查询模式切换，逗号分隔输入 | `frontend/src/App.vue` | 页面切换到向量查询模式，输入逗号分隔向量后返回 Top-K |
| [ ] | 同一页面支持索引切换对比 | 已能选择索引，但无对比呈现 | `frontend/src/App.vue`、`backend/app/api/search.py`、`backend/app/services/search.py` | 同一查询可切换 `flat` 与 `hnsw/ivf`，展示不同耗时 |
| [x] | 展示索引构建耗时 | 前端已增加构建索引按钮和耗时展示 | `frontend/src/App.vue` | 构建索引后页面显示 `build_ms` |
| [x] | 条件检索可稳定演示 | 已有 `cell_type` 过滤雏形 | `backend/app/services/search.py`、`backend/app/api/search.py`、`frontend/src/App.vue` | 输入 `cell_type` 后结果只返回该类型细胞 |
| [ ] | 增加简单结果可视化 | 当前只有表格 | `frontend/src/App.vue`、`frontend/src/style.css` | 用距离条形图、类型分布或查询摘要展示 Top-K 结果 |
| [ ] | 增加演示数据说明卡片 | 当前状态栏信息较少 | `frontend/src/App.vue`、`README.md` | 页面展示数据集名称、细胞数、维度、当前索引和可用元信息字段 |
| [ ] | 增加轻量 API 测试 | 当前没有测试文件 | `backend/tests/test_search_api.py`、`backend/requirements.txt` | 测试覆盖健康检查、建索引、查询成功和错误参数 |
| [x] | 补充中期演示脚本 | README 已有 5-8 分钟演示流程 | `README.md` 或 `doc/` 下演示说明文档 | 按脚本能稳定完成 5-8 分钟演示 |

### 2.3 P2：中期可以不实现的内容

| 检查项 | 中期处理方式 | 结项阶段建议 |
| --- | --- | --- |
| 用户注册、登录、管理员管理 | 可以保留接口骨架，并说明不是中期主线 | 接入用户模型、密码哈希、会话或 JWT、角色权限 |
| 数据上传 | 可以不做页面上传，演示时使用 demo 或固定路径数据 | 实现文件上传、格式校验、数据集元信息管理 |
| 多数据集管理 | 可以只保留当前单数据集 | 增加数据集列表、切换、删除和状态管理 |
| 索引保存与加载 | 可以不暴露 API，只保留索引类方法 | 增加索引文件管理、保存、加载、失效判断 |
| 完整性能评测接口 | 可以不做系统性评测 | 实现 Recall@k、平均查询时间、构建时间、多 Top-K 对比 |
| 复杂交互式可视化 | 可以只做表格或简单条形图 | 增加 UMAP/散点图、高亮查询点和相似结果 |
| 数据库持久化 | 可以不引入数据库 | 保存用户、数据集、索引、查询记录和评测记录 |
| 完整测试报告 | 中期可只做轻量自检 | 结项补功能测试、性能测试和测试环境说明 |
| 完整用户手册和演示视频材料 | 中期只需准备现场演示说明 | 结项补安装说明、使用说明、常见问题和演示视频 |

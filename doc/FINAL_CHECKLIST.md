# 结项代码任务清单

本文档承接 [`MID_TERM_CHECKLIST.md`](./MID_TERM_CHECKLIST.md)。中期主链路(数据读取 → 向量化 → ANN 索引构建 → Top-K 检索 → Web 展示)的 **P0/P1 已全部完成**。本清单把中期推迟到结项阶段的 **P2 代码功能**拆成一条条可执行、可打勾、带验收方式的任务,照此逐项推进即可。

> 本文档只覆盖**代码功能**。开发文档、贡献度说明、用户手册、演示视频等**提交交付物**见 [`FINAL_SUBMISSION.md`](./FINAL_SUBMISSION.md),不在本清单内。

## 一、结项目标

在中期主链路之上,补齐 README 功能表里承诺过、但中期以骨架形式保留的模块,使"用户信息 / 性能评测 / 数据管理"从 `501` 骨架变为可演示的完整功能。

## 二、方案选型(可调整)

| 项 | 选型 | 说明 |
| --- | --- | --- |
| 持久化 | **SQLite + SQLAlchemy** | 零配置、文件型数据库,同时勾掉 P2「数据库持久化」项 |
| 登录态 | **JWT(PyJWT)** | 适合 Vue SPA 前后端分离;前端存 `localStorage`,请求带 `Authorization` 头 |
| 密码 | **werkzeug 哈希** | `generate_password_hash` / `check_password_hash`,不引入额外依赖 |
| 范围 | 模块 A/B/C 必做,模块 D 可选加分 | UMAP 可视化、查询记录落库为提分项,时间紧可跳过 |

## 三、优先级定义

- `P0`:结项必须完成。缺失会导致 README 功能表与实际功能对不上。
- `P1`:建议完成,提升完整度与评分上限。
- `P2`:可选加分,时间不足可明确说明为未来工作。

---

## 四、任务清单

### 模块 A · 性能评测 `/api/eval`(P0)

以 `flat` 精确检索结果作为 ground truth,评测各 ANN 索引的召回率与耗时。README 已在 API 概览里承诺该模块。

| 完成 | 任务 | 涉及文件 | 验收方式 |
| --- | --- | --- | --- |
| [x] | A1 评测服务:抽样 `n_queries` 个细胞作查询,`flat` 结果作 ground truth,计算目标索引 `recall@k` | `backend/app/services/eval.py`(新增),复用 `search_service`、`create_index`、`FlatIndex` | 单测传入 demo 数据,`flat` 自比召回率为 `1.0` |
| [ ] | A2 `POST /api/eval`:入参 `index_types[]`、`top_k`、`n_queries`、`metric`;返回每个索引的 `recall@k`、平均 `query_ms`、`build_ms` | `backend/app/api/eval.py`(改写,去掉 501) | POST 返回各索引对比数组;非法 `index_type` 返回 400 |
| [ ] | A3 前端评测面板:一键触发评测,表格展示多索引 `recall@k / 平均查询耗时 / 构建耗时` 对比,附简单柱状图 | `frontend/src/App.vue`、`frontend/src/style.css` | 页面点击「性能评测」后出现对比表,数值与后端一致 |
| [ ] | A4 评测 API 轻量测试 | `backend/tests/test_eval_api.py`(新增) | 覆盖:评测成功返回结构、非法索引类型报错 |

### 模块 B · 用户注册 / 登录 / 管理员 + SQLite(P0 主体,P1 前端与管理员)

| 完成 | 任务 | 涉及文件 | 验收方式 |
| --- | --- | --- | --- |
| [ ] | B1 引入 SQLAlchemy:加依赖、加 `SQLALCHEMY_DATABASE_URI`、在应用工厂初始化 `db` 并建表 | `backend/requirements.txt`、`backend/app/core/config.py`、`backend/app/core/extensions.py`(新增)、`backend/app/__init__.py` | 后端启动后自动生成 `.db` 文件,无报错 |
| [ ] | B2 `User` 模型:`id/username/password_hash/role/created_at`,含密码哈希与校验方法 | `backend/app/models/user.py`(新增)、`backend/app/models/__init__.py` | 可创建用户,`role` 支持 `admin`/`user` |
| [ ] | B3 `register` / `login`:参数校验、用户名唯一、密码哈希、登录签发 JWT | `backend/app/api/auth.py`(改写,去掉 501) | 注册后可登录并拿到 token;重复用户名 / 错误密码返回 400 |
| [ ] | B4 JWT 鉴权装饰器 + 管理员用户管理(用户列表、删除用户,仅 admin 可用) | `backend/app/core/security.py`(新增)、`backend/app/api/auth.py` | 无 / 非法 token 返回 401;非 admin 访问管理接口返回 403 |
| [ ] | B5 首次启动播种默认 admin 账号(用户名/密码写入 README) | `backend/app/__init__.py` 或启动脚本 | 全新库启动后用默认 admin 能登录 |
| [ ] | B6 前端:登录 / 注册表单,token 存 `localStorage`,请求统一带 `Authorization`;管理员可见用户管理视图 | `frontend/src/App.vue`、`frontend/src/style.css` | 登录后展示当前用户;admin 登录可看到并删除用户 |
| [ ] | B7 用户 API 轻量测试 | `backend/tests/test_auth_api.py`(新增) | 覆盖:注册、登录、鉴权失败、admin 权限校验 |

### 模块 C · 数据集删除 + 索引持久化(P1)

索引类已有 `save/load`,但未接 API;数据集删除仍是 501。

| 完成 | 任务 | 涉及文件 | 验收方式 |
| --- | --- | --- | --- |
| [ ] | C1 索引持久化服务:`build` 后可存到 `INDEX_DIR`,可从磁盘加载;`status` 增加持久化标记 | `backend/app/services/search.py`、`backend/app/core/config.py`（`INDEX_DIR`） | 保存后 `INDEX_DIR` 出现索引文件,重启后可加载查询 |
| [ ] | C2 `POST /api/index/save`、`POST /api/index/load` | `backend/app/api/index.py` | 保存返回文件信息;加载后 `/api/search` 能继续查询 |
| [ ] | C3 `DELETE /api/datasets/<name>`:删除 data 目录文件并清理关联索引,复用 `_resolve_h5ad_path` 安全校验 | `backend/app/api/datasets.py`(改写,去掉 501) | 删除后 `/api/datasets` 不再列出;越权路径 / 不存在返回 400 |
| [ ] | C4 前端:数据集删除按钮 + 索引保存 / 加载按钮 | `frontend/src/App.vue` | 页面可保存 / 加载索引,可删除非当前数据集 |
| [ ] | C5 数据管理 / 索引持久化测试 | `backend/tests/`(可并入现有测试或新增) | 覆盖:保存加载往返、删除成功、非法删除报错 |

### 模块 D · 可选加分(P2)

| 完成 | 任务 | 涉及文件 | 验收方式 |
| --- | --- | --- | --- |
| [ ] | D1 查询记录落库:`QueryLog` 模型(cell_id/top_k/index_type/query_ms/时间),检索时写入 | `backend/app/models/query_log.py`(新增)、`backend/app/services/search.py` | 查询后数据库出现记录;可选提供查询历史接口 |
| [ ] | D2 UMAP 2D 可视化:后端算 2D 坐标接口,前端散点图高亮查询点与 Top-K 结果 | 新增服务 + `frontend/src/App.vue`,依赖 `umap-learn` | 页面展示 2D 散点,查询点与相似结果被高亮 |

### 模块 E · 收尾同步(P0)

| 完成 | 任务 | 涉及文件 | 验收方式 |
| --- | --- | --- | --- |
| [ ] | E1 更新 README:API 概览去掉 auth/eval 的"预留"字样,更新"当前限制" | `README.md` | README 描述与实际功能一致 |
| [ ] | E2 维护本清单勾选状态,结项前全部 P0/P1 打勾 | 本文档 | 逐项复核通过 |

---

## 五、建议实现顺序

`A（评测，独立、无DB依赖，最快出成果）` → `B（用户+SQLite，引入 DB 基座）` → `C（数据集/索引管理）` → `D（可选加分）` → `E（收尾）`。

每完成一个模块:补对应轻量测试 → 本地 `pytest` 通过 → 前端联调一次 → 更新本清单勾选与 README。

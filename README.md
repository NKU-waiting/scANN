# scANN：单细胞近似最近邻检索系统

scANN 是一个面向单细胞高维向量的课程级 Web 检索系统。后端使用 Flask、SQLAlchemy、NumPy、FAISS 和 UMAP，前端使用 Vue 3 与 Vite。系统覆盖数据导入、精确/近似索引、条件 Top-K 查询、多数据集联合检索、性能评测、二维结果展示、账户与管理员管理，以及数据集和索引持久化。

## 已完成功能

| 模块 | 能力 |
| --- | --- |
| 用户与权限 | 注册、登录、JWT、实时用户校验、管理员用户管理、业务 API 登录门禁 |
| 数据管理 | demo 数据；`.h5ad`、`.npy`、`.csv` 上传；列表、切换、重启恢复、指纹校验、删除 |
| 索引管理 | NumPy Flat；FAISS Flat、IVF、HNSW、PQ；构建、保存、清单校验、加载、列出、删除 |
| 查询检索 | 细胞编号或向量查询；L2、Cosine、IP；Top-K；`cell_type` 保证型条件检索 |
| 联合检索 | 多数据集联合建索引；共享空间确认；复合细胞身份；跨数据集来源追踪与条件检索 |
| 评测分析 | Flat ground truth、Recall@K、平均查询耗时、构建耗时、多索引对比 |
| 可视化 | 结果表、距离/得分条形图、类型分布、UMAP/PCA 散点图与查询/近邻高亮 |
| 运行历史 | 查询与评测记录入库；原始查询向量不落库；用户隔离和管理员全局视图 |
| 工程质量 | 后端 pytest/Ruff，前端 Vitest/ESLint/生产构建，GitHub Actions 双端质量门 |

## 架构概览

```text
Vue SPA
  │  Bearer JWT + JSON / multipart
  ▼
Flask API ── SQLAlchemy/SQLite（用户、数据集、索引元信息、历史）
  │
  ├─ 数据加载：AnnData / NumPy / CSV
  ├─ 检索：NumPy Flat / FAISS Flat、IVF、HNSW、PQ
  ├─ 联合检索：共享向量空间中的多数据集快照 + 来源映射
  ├─ 评测：Flat ground truth + Recall@K
  └─ 可视化：UMAP / PCA 投影

本地文件系统：上传数据、索引文件、校验清单、运行日志
```

后端以服务层封装数据、索引、查询、评测、历史与投影逻辑；API 处理认证和请求契约；前端通过统一 API 客户端访问。数据文件与索引文件不进入 Git，数据库只保存元信息和运行记录。

## 环境要求

- Python 3.12
- Node.js 22.13+ 或 24.x LTS
- npm
- Miniconda 或兼容的 conda

## 快速开始

### 1. 创建环境并安装后端

```bash
conda create -n scann python=3.12 -y
conda activate scann
cd backend
pip install -r requirements.txt
```

开发演示可直接启动；首次启动会创建 SQLite 表和 demo 管理员：

```bash
python run.py
```

默认监听 `http://127.0.0.1:5000`。开发默认管理员为 `admin` / `admin123`，只用于本机演示。生产模式会拒绝默认密钥和默认管理员密码。

需要自定义配置时，将项目根目录的 `.env.example` 复制为 `backend/.env`，或显式导出变量，并至少替换以下值：

```text
SCANN_SECRET_KEY
SCANN_ADMIN_PASSWORD
SCANN_CORS_ORIGINS
```

### 2. 安装并启动前端

```bash
cd frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`。开发服务器会把 `/api` 代理到后端。

如果后端不在默认地址运行，将 `frontend/.env.example` 复制为 `frontend/.env`，再设置 `VITE_API_PROXY_TARGET`。该值应与后端的 `SCANN_HOST` / `SCANN_PORT` 保持一致。

### 3. 完成一次完整流程

1. 登录或注册。
2. 使用 demo 数据，或在“数据集管理”上传支持的文件。
3. 选择索引和度量，构建索引。
4. 按细胞编号或向量执行 Top-K 查询，可填写 `cell_type`。
5. 保存当前索引；构建其他索引后可重新加载已保存索引。
6. 上传至少两个同空间数据集后，可填写共享空间标识，构建联合索引并执行跨数据集查询。
7. 查看 UMAP/PCA、索引对比、性能评测和运行历史。
8. 管理员可删除非活动数据集、非活动索引和普通用户。

## 数据格式

- `.h5ad`：默认优先使用 `obsm[X_pca]`，字段不存在时回退到 `X`；也可在上传界面指定其他 `obsm` 字段或 `X`。
- `.npy`：二维有限数值矩阵，形状为“细胞 × 特征”；禁止 pickle 对象数组。
- `.csv`：支持纯数值矩阵；带表头时可用 `cell_id` 指定细胞名、用 `obs:<字段名>` 声明元数据列，其余列为数值特征。

上传文件会先写入临时文件，解析、维度、有限数和格式校验通过后再原子发布。语义 SHA-256 指纹同时绑定源文件、H5AD 表示选择、实际向量和细胞顺序，因此会拒绝外部篡改或跨表示索引串用。

## API 摘要

除健康检查、注册和登录外，所有业务接口都需要 `Authorization: Bearer <token>`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| POST | `/api/auth/register`、`/api/auth/login` | 注册、登录 |
| GET | `/api/auth/me` | 校验当前登录态 |
| GET/POST | `/api/datasets`、`/api/datasets/upload` | 列表、上传 |
| POST | `/api/datasets/<id>/activate` | 切换数据集 |
| DELETE | `/api/datasets/<id>` | 管理员删除非活动数据集 |
| GET/POST | `/api/index/status`、`/api/index/build` | 索引状态、构建 |
| GET/POST | `/api/index/artifacts`、`/api/index/save`、`/api/index/load` | 持久化索引管理 |
| POST | `/api/search` | 条件 Top-K 检索 |
| GET/POST | `/api/federated/index/status`、`/api/federated/index` | 联合索引状态、构建 |
| POST | `/api/federated/search` | 跨数据集 Top-K 检索 |
| POST | `/api/eval` | 多索引性能评测 |
| GET | `/api/visualization/embedding` | UMAP/PCA 二维投影 |
| GET | `/api/history/queries`、`/api/history/evaluations` | 查询与评测历史 |

完整契约见 [API 文档](doc/API.md)。

## 质量验证

后端：

```bash
conda activate scann
cd backend
ruff check .
ruff format --check .
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
```

前端：

```bash
conda activate scann
cd frontend
npm run lint
npm test
npm run build
```

永久回归测试使用临时目录和临时数据库，不向仓库写入数据、索引或测试结果。CI 会执行同一组质量门。

## 配置与安全

- `SCANN_ENV=production` 时，密钥少于 32 字符、默认管理员密码或 DEBUG 会导致启动失败。
- CORS 默认只允许本机 Vite 开发地址，可通过 `SCANN_CORS_ORIGINS` 配置。
- JWT 每次请求都会查询当前数据库用户并校验不可复用的登录版本；用户删除或数字 ID 复用后旧 token 仍然失效。
- 数据路径、索引路径和文件名均经过目录边界与指纹校验。
- 查询历史不保存原始向量；日志不记录 token、密码或上传内容。
- 上传上限、Top-K、评测查询数、可视化点数、联合数据集数和联合细胞总数均可配置且有服务端上界。

后端配置示例见 [.env.example](.env.example)，开发代理示例见 [frontend/.env.example](frontend/.env.example)。

## 项目文档

- [需求分析](doc/REQUIREMENT.md)
- [完整 API 契约](doc/API.md)
- [用户手册](doc/USER_GUIDE.md)
- [测试与验收说明](doc/TESTING.md)
- [结项交付说明](doc/FINAL_SUBMISSION.md)
- [结项功能清单](doc/FINAL_CHECKLIST.md)

## 当前边界

本项目面向单机课程演示。活动数据集、已加载索引和联合索引在单进程内共享；数据库、上传文件和单数据集索引文件可跨重启恢复，但联合索引需在进程重启后重建，也不支持多进程 worker 之间的活动状态同步。联合检索只验证维度并要求用户确认共享 embedding 空间，不会自动对齐不同 PCA 基底或执行批次校正。UMAP 首次运行需要 Numba 编译，后续会使用运行时缓存。系统不包含原始测序质控、复杂生物学注释、多租户隔离或工业级任务队列。

真实数据来源、许可、成员贡献度、远程仓库链接和演示视频属于项目组提交信息，需在交付前由负责人补充，仓库不会虚构这些内容。

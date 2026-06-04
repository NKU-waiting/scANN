# scANN — 单细胞近似最近邻（ANN）检索系统

面向单细胞高维向量数据的 **近似最近邻（Approximate Nearest Neighbor）检索系统**，
为大规模单细胞数据（细胞 × 基因表达矩阵经降维后的高维向量）提供高效的相似样本检索能力。

> 软件工程课程大作业。技术栈：**Flask（REST API）+ Vue3（前端）+ FAISS（ANN 核心）**。

---

## 功能模块

| 模块 | 说明 | 状态 |
| --- | --- | --- |
| 用户信息模块 | 注册 / 登录，管理员用户管理 | P2：结项完善 |
| 数据管理模块 | demo 数据初始化、`.h5ad` 读取函数、数据集 API 骨架 | P0/P1：中期优先保证 demo 主链路，可选接通 `.h5ad` |
| 索引构建模块 | 索引构建、状态查询、可插拔索引接口 | P0：Flat + 至少一种 FAISS ANN |
| 查询检索模块（核心） | 输入细胞编号，返回 Top-K 相似结果 | P0：中期核心功能 |
| 可视化展示模块 | 前端查询表单、结果表格、查询耗时、索引状态 | P0：中期核心展示 |
| 性能评测模块 | 召回率 / 批量查询 / 多索引对比 | P2：结项完善，P1 可做简单耗时对比 |

---

## 中期检查范围

中期检查的完整[CHECKLIST](./doc/MID_TERM_CHECKLIST.md)，中期的目标是跑通并展示完整主链路：

```text
单细胞数据读取 → 向量化表示 → ANN 索引构建 → Top-K 相似细胞检索 → Web 展示
```

优先级说明：

- `P0`：中期必须完成的最小实现。
- `P1`：建议完成的加分项，用于提升展示完整度。
- `P2`：中期可以不实现，推迟到结项阶段。

---

## 目录结构

```
scANN/
├── backend/                  # Flask REST API
│   ├── app/
│   │   ├── __init__.py       # 应用工厂 create_app()
│   │   ├── api/              # 路由蓝图: auth / datasets / index / search / eval
│   │   ├── core/            # 配置、扩展
│   │   ├── services/
│   │   │   ├── data_loader.py    # .h5ad 读取与预处理（含假数据生成）
│   │   │   ├── index/            # 可插拔索引: base / faiss_index / flat_index
│   │   │   └── search.py         # Top-K 检索服务
│   │   └── models/          # 用户 / 数据集 数据模型（预留）
│   ├── requirements.txt
│   └── run.py               # 入口: python run.py
├── frontend/                 # Vue3 + Vite，查询页 + 结果展示骨架
├── data/                     # 数据集存放（默认 gitignore）
├── doc/                      # 实验要求、需求分析、中期检查清单
└── README.md
```

---

## 快速开始

### 1. 后端（Flask）

创建并进入 Python 环境：

```bash
conda create -n scann python=3.12 -y
conda activate scann
```

安装依赖并启动后端：

```bash
cd backend
pip install -r requirements.txt
python run.py
```

服务默认启动在 `http://127.0.0.1:5000`。

> 说明：`requirements.txt` 中 `faiss-cpu` 为核心 ANN 库。`flat` 索引使用内置 NumPy 暴力检索，可作为精确检索基线；如果需要展示 `hnsw`、`ivf` 等 ANN 索引，需要确保 FAISS 依赖安装成功。

#### 验证最小检索流程

```bash
# 健康检查
curl http://127.0.0.1:5000/api/health

# 查看当前 demo 数据集和索引状态
curl http://127.0.0.1:5000/api/index/status

# 构建 Flat 精确索引
curl -X POST http://127.0.0.1:5000/api/index/build \
  -H "Content-Type: application/json" \
  -d '{"index_type": "flat", "metric": "l2"}'

# 构建一种 FAISS ANN 索引
curl -X POST http://127.0.0.1:5000/api/index/build \
  -H "Content-Type: application/json" \
  -d '{"index_type": "hnsw", "metric": "l2"}'

# 用随机生成的演示数据检索 Top-5
curl -X POST http://127.0.0.1:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"cell_id": 0, "top_k": 5, "index_type": "flat", "metric": "l2"}'
```

### 2. 前端（Vue3 + Vite）

```bash
cd frontend
npm install
npm run dev
```

前端默认 `http://127.0.0.1:5173`，已配置代理将 `/api` 转发到后端 `5000` 端口。

---

## 中期演示流程

建议按以下顺序进行 5-8 分钟展示：

1. 启动后端服务，访问 `/api/health`。
2. 启动前端页面，展示当前 demo 数据集状态。
3. 使用 `flat` 索引执行一次 Top-K 查询。
4. 切换到 `hnsw` 或 `ivf` 索引，再执行一次相同查询。
5. 对比查询耗时和返回结果。
6. 展示结果表格中的细胞编号、名称、元信息和距离。
7. 可选展示 `cell_type` 条件过滤、向量查询或真实 `.h5ad` 数据加载。

---

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET  | `/api/health` | 健康检查 |
| GET  | `/api/datasets` | 数据集列表 |
| POST | `/api/index/build` | 构建索引（index_type, metric） |
| GET  | `/api/index/status` | 当前索引状态 |
| POST | `/api/search` | Top-K 相似细胞检索（核心） |
| POST | `/api/eval` | 性能评测（耗时 / 召回率，预留） |
| POST | `/api/auth/register` `/api/auth/login` | 用户注册 / 登录（预留） |

---

## 当前限制

- 当前主线默认使用 demo 数据，真实 `.h5ad` 加载属于中期 P1 加分项。
- 当前系统以单进程内存状态管理“当前数据集 + 当前索引”，尚未接入数据库。
- 索引类已有 `save/load` 接口，但索引持久化和动态管理尚未接入 API。
- 用户注册、登录、管理员管理、完整性能评测和复杂可视化推迟到结项阶段。

---

## 技术选型说明

- **ANN 核心：FAISS** — 支持 IVF / PQ / HNSW，便于性能评测对比；提供 Flat 暴力检索作为基线与回退。
- **可插拔索引接口** `BaseIndex`：新增算法只需实现 `build / search / save / load`。
- **数据格式：AnnData（.h5ad）** — 单细胞分析生态标准结构，`X` 为细胞 × 基因表达矩阵。

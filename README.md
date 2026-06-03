# scANN — 单细胞近似最近邻（ANN）检索系统

面向单细胞高维向量数据的 **近似最近邻（Approximate Nearest Neighbor）检索系统**，
为大规模单细胞数据（细胞 × 基因表达矩阵经降维后的高维向量）提供高效的相似样本检索能力。

> 软件工程课程大作业。技术栈：**Flask（REST API）+ Vue3（前端）+ FAISS（ANN 核心）**。

---

## 功能模块

| 模块 | 说明 | 状态 |
| --- | --- | --- |
| 用户信息模块 | 注册 / 登录，管理员用户管理 | 🚧 接口预留 |
| 数据管理模块 | `.h5ad` 数据导入、读取、组织、格式校验、预处理 | 🚧 骨架 |
| 索引构建模块 | 索引的构建 / 保存 / 加载，可插拔索引接口 | ✅ 接口 + FAISS/Flat 实现 |
| 查询检索模块（核心） | 输入细胞编号或向量，返回 Top-K 相似结果 | ✅ 最小可运行示例 |
| 可视化展示模块 | 检索结果展示（前端） | 🚧 骨架 |
| 性能评测模块 | 召回率 / 查询耗时等指标 | 🚧 接口预留 |

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
├── docs/                     # 软件开发文档（对应五大块要求）
└── README.md
```

---

## 快速开始

### 1. 后端（Flask）

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

服务默认启动在 `http://127.0.0.1:5000`。

> 说明：`requirements.txt` 中 `faiss-cpu` 为核心 ANN 库。若安装遇到问题，系统会自动回退到
> 内置的 **Flat（numpy 暴力检索）** 实现，仍可跑通最小检索流程。

#### 验证最小检索流程

```bash
# 健康检查
curl http://127.0.0.1:5000/api/health

# 用随机生成的演示数据构建索引并检索 Top-5
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

## 技术选型说明

- **ANN 核心：FAISS** — 支持 IVF / PQ / HNSW，便于性能评测对比；提供 Flat 暴力检索作为基线与回退。
- **可插拔索引接口** `BaseIndex`：新增算法只需实现 `build / search / save / load`。
- **数据格式：AnnData（.h5ad）** — 单细胞分析生态标准结构，`X` 为细胞 × 基因表达矩阵。

详见 `docs/` 下的开发文档。

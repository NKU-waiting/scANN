# scANN 前端

Vue 3 + Vite 单页工作台，覆盖：

- 登录、注册和 token 失效处理；
- 管理员用户列表与删除；
- 数据集上传、列表、切换和删除；
- 索引构建、保存、加载和删除；
- 细胞/向量查询、条件过滤和索引对比；
- 多数据集联合检索与证据约束自然语言 RAG；
- Recall@K、查询/构建耗时、序列化索引字节和 PQ 精确重排成对评测；
- 结果表、条形图、类型分布、UMAP/PCA SVG；
- 查询与评测历史。

## 环境与命令

要求 Node.js 22.13+ 或 24.x LTS。先启动后端，再执行：

```bash
npm ci
npm run dev
```

开发服务器监听 5173，并将 `/api` 代理到后端 5000 端口。修改后端地址时，复制 `.env.example` 为 `.env` 并设置 `VITE_API_PROXY_TARGET`。

质量门：

```bash
npm run lint
npm test
npm run build
```

Vitest 使用 jsdom，不需要启动真实后端。`npm run preview` 只预览静态产物，不提供 API 反向代理；独立部署时应让同源 Web 服务器把 `/api` 转发到 Flask，并配置后端 CORS 允许列表。

## 结构

- `src/App.vue`：认证、查询、对比和评测工作台编排；
- `src/api.js`：统一 Bearer token、JSON/multipart 和错误处理；
- `src/components/DatasetManager.vue`：数据集生命周期；
- `src/components/IndexManager.vue`：持久化索引管理；
- `src/components/FederatedSearch.vue`：共享空间多数据集联合检索；
- `src/components/CellAssistant.vue`：自然语言计划、证据与可选 AI 回答；
- `src/components/EmbeddingPlot.vue`：UMAP/PCA SVG；
- `src/components/HistoryPanel.vue`：查询/评测历史；
- `src/*.test.js`、`src/components/*.test.js`：前端回归测试。

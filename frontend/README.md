# scANN 前端（Vue3 + Vite）

```bash
npm install
npm run dev      # http://127.0.0.1:5173
```

`/api` 已通过 Vite 代理转发到后端 `http://127.0.0.1:5000`，开发时需先启动后端（见根目录 README）。

## 结构
- `src/App.vue` — 查询页：参数设置 + Top-K 结果表 + 索引状态展示（可视化模块的骨架）。
- `vite.config.js` — 开发服务器与 `/api` 代理配置。

后续可扩展：结果的散点/降维可视化、数据集管理页、评测图表页。

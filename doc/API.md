# scANN API 契约

本文档描述当前实现的 HTTP API。除健康检查、注册和登录外，所有接口都要求：

```http
Authorization: Bearer <JWT>
```

JSON 错误统一包含 `error`；框架级错误还包含 `status`。参数错误通常返回 `400`，未认证返回 `401`，权限不足返回 `403`，资源不存在返回 `404`，资源状态冲突返回 `409`。

## 健康与认证

### `GET /api/health`

公开健康检查，返回服务名、状态和版本。

### `POST /api/auth/register`

```json
{"username": "alice", "password": "pass123"}
```

用户名最长 64 字符，密码至少 6 字符。注册成功返回 `201`。公开注册只能创建普通用户。

### `POST /api/auth/login`

请求体同注册。成功返回 JWT 和用户对象；token 有效期 24 小时。

### `GET /api/auth/me`

校验 token 对应的用户仍然存在、登录版本未变更，并返回数据库中的实时角色。

### `GET /api/auth/users`

仅管理员。返回用户列表。

### `DELETE /api/auth/users/<user_id>`

仅管理员。不能删除当前登录管理员，也不能删除最后一个管理员。删除用户会在同一提交中清理其查询/评测历史，旧 token 不会因数字 ID 复用而恢复有效。

## 数据集

### `GET /api/datasets`

返回 demo 和所有持久化数据集。每个资源包含规模、格式、指纹、元数据字段、活动状态和是否可删除。

### `POST /api/datasets/upload`

使用 `multipart/form-data`：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | `.h5ad`、`.npy` 或 `.csv` |
| `name` | 否 | 1–100 字符；默认使用文件名；不区分大小写判重 |
| `use_obsm` | 否 | `.h5ad` 向量字段，默认 `X_pca`；填 `X` 使用表达矩阵 |
| `activate` | 否 | 默认 `true`，上传成功后切换为活动数据集 |

文件先进入临时位置，通过格式、维度、有限数和索引构建校验后再发布。成功返回 `201`。

### `POST /api/datasets/<dataset_id>/activate`

加载并校验数据文件，原子切换活动数据集，同时建立 Flat/L2 基线索引。

### `POST /api/datasets/demo/activate`

切换到可复现 demo 数据。

### `POST /api/datasets/load`

兼容入口：

- `{"dataset_id": 1}`：激活持久化数据集；
- `{"path": "example.h5ad", "name": "example"}`：从数据目录内安全复制并纳管文件；
- `{}`：激活 demo。

路径必须是数据目录内的相对路径，拒绝绝对路径、目录穿越和不支持的扩展名。

### `DELETE /api/datasets/<dataset_id>`

仅管理员。活动数据集不能删除。删除会在同一事务语义下清理关联索引记录、索引文件和清单。

## 索引

### `GET /api/index/status`

返回活动数据集、数据集指纹、索引类型、度量、规模、元数据字段、就绪状态和持久化索引 ID。`limits` 同时返回 `max_top_k`、`max_eval_queries` 和 `max_visualization_points`，前端使用这些值设置输入上限。

### `POST /api/index/build`

```json
{"index_type": "hnsw", "metric": "cosine"}
```

`index_type` 支持 `flat`、`faiss`、`ivf`、`hnsw`、`pq`、`pq_rerank`；`metric` 支持 `l2`、`cosine`、`ip`。`pq_rerank` 先取 4 倍 PQ 候选，再使用已加载原始向量按真实度量重排。构建在候选对象上完成，成功后才替换当前索引。

### `GET /api/index/artifacts`

列出持久化索引。可用 `dataset_id` 查询参数过滤。`compatible` 只在索引的数据集 ID 和语义指纹都匹配当前数据集时为真。

### `POST /api/index/save`

```json
{"name": "demo-hnsw-cosine"}
```

名称可省略。系统写入索引文件、JSON 清单和数据库记录，并记录数据集/文件指纹、算法参数、维度、条目数和库版本。成功返回 `201`。

### `POST /api/index/load`

```json
{"index_id": 1}
```

加载前校验清单、文件指纹、数据集 ID/语义指纹、维度、条目数、度量和参数。任何校验失败都不会替换当前索引。

### `DELETE /api/index/artifacts/<index_id>`

仅管理员。当前加载的持久化索引不能删除，应先构建或加载其他索引。

## 查询

### `POST /api/search`

按细胞编号：

```json
{
  "cell_id": 0,
  "top_k": 5,
  "index_type": "hnsw",
  "metric": "cosine",
  "cell_type": "type_1"
}
```

按向量：

```json
{
  "vector": [0.1, 0.2, 0.3],
  "top_k": 5,
  "index_type": "flat",
  "metric": "l2"
}
```

`cell_id` 与 `vector` 必须且只能提供一个。向量必须是一维、有限数值且维度匹配。`top_k` 必须为正整数且不超过服务端上限。

响应中的 `score_kind` 定义数值语义：

- `squared_l2_distance`：平方 L2 距离，越小越近；
- `cosine_distance`：`1 - cosine_similarity`，越小越近；
- `inner_product`：内积，越大越相似，响应中的 `higher_is_better` 为 `true`。

`cell_type` 条件存在时，系统在满足条件的子集上执行精确回退，保证所有返回项满足条件，数量为 `min(top_k, 候选数)`。

成功查询会写入历史并返回 `query_id`，但原始查询向量不会落库。

## 多数据集联合检索

联合检索只接受受管理数据集，不把 demo 数据加入集合。所选数据集必须具有相同向量维度；此外，调用方必须提供共享向量空间标识并确认向量确实由相同特征顺序或同一 embedding 模型产生。服务不会把两个维度相同但基底不同的 PCA 自动对齐。

### `GET /api/federated/index/status`

返回进程内联合索引状态、成员数据集、联合指纹、共享空间标识、规模、算法参数与兼容性声明。成员数据集删除后，引用它的联合索引立即失效。

### `POST /api/federated/index`

```json
{
  "dataset_ids": [1, 2],
  "embedding_space": "atlas-pca-v1",
  "confirm_shared_space": true,
  "index_type": "hnsw",
  "metric": "cosine"
}
```

`dataset_ids` 至少包含两个不重复的正整数。服务按数据集 ID 规范化成员顺序，逐个校验文件与语义指纹，再在候选对象上构建联合索引；全部成功后才发布。联合指纹绑定共享空间标识、成员 ID 和成员指纹。数据集数量与细胞总数分别受 `SCANN_MAX_FEDERATED_DATASETS` 和 `SCANN_MAX_FEDERATED_CELLS` 限制。

### `POST /api/federated/search`

按联合成员中的细胞查询：

```json
{"query_dataset_id": 1, "cell_id": 7, "top_k": 10, "cell_type": "T cell"}
```

也可提供 `vector` 代替 `query_dataset_id + cell_id`。结果行包含 `dataset_id`、`dataset`、本地 `cell_id`、`cell_name`、联合 `global_cell_id` 和稳定的 `composite_id`。按细胞查询只排除该数据集中的查询细胞，不会错误排除另一个数据集中具有相同本地编号的细胞。`cell_type` 存在时，在所有成员数据集的匹配子集上执行精确检索。

## RAG 单细胞分析助手

### `GET /api/assistant/status`

返回 AI provider 是否完整配置、模型标识、本地证据降级能力和问题/证据/细胞资源上限。响应不包含 API key 或 provider 地址。

### `POST /api/assistant/query`

自然语言解析查询细胞：

```json
{
  "question": "请找出与 study-a/a0 最相似的 5 个细胞，并总结类型和来源。",
  "dataset_ids": [1, 2],
  "embedding_space": "atlas-pca-v1",
  "confirm_shared_space": true,
  "top_k": 5,
  "use_ai": true
}
```

也可显式提供 `query_dataset_id + cell_id`、`cell_type` 和 `metric`；这些字段仍由服务端校验。`dataset_ids` 是不可由问题或模型扩大的硬范围。多数据集请求必须满足共享空间契约；单数据集请求不需要该字段。

成功响应包含：

- `plan`：`similar_to_cell`、`cell_type_representatives` 或 `dataset_summary` 受限计划；
- `evidence`：带 `[E#]`、来源、本地身份、类型、数值和数值语义的细胞证据；
- `citations`：回答实际引用的 `[D#]` 数据集或 `[E#]` 细胞；
- `generator`：`openai_responses` 或 `local_grounded`，以及安全的模型/用量信息；
- `grounding`：集合指纹、证据数及“未暴露原始向量/非生物学定论”标志。

provider 未配置时返回 `200`、`local_grounded` 和 warning。provider 超时、非法结构或越权引用返回 `502`。服务不保存问题/回答或原始向量。完整数据流、Responses 契约与安全边界见 [RAG 助手说明](RAG_ASSISTANT.md)。

## 性能评测

### `POST /api/eval`

```json
{
  "index_types": ["flat", "ivf", "hnsw", "pq", "pq_rerank"],
  "top_k": 10,
  "n_queries": 100,
  "metric": "l2"
}
```

Flat 精确结果作为 ground truth。每个索引返回 `recall_at_k`、`avg_query_ms`、`build_ms`、`index_bytes`、`bytes_per_vector`、`index_fingerprint`、实际参数、查询种子/摘要和边界修正后的 `effective_top_k`。`index_bytes` 是稳定的序列化索引大小代理，不是进程 RSS。当请求 K 超过可用邻居数时，Recall 分母使用真实可用邻居数。成功评测返回 `evaluation_id` 并保存结果快照。

同一请求同时包含 `pq` 和 `pq_rerank` 时，顶层 `ann_improvement` 校验两行使用相同查询摘要和相同 PQ 序列化指纹，并返回 Recall、平均查询耗时和索引字节差值。只有基础索引指纹一致时才声明候选超集重排保证。重排的理论保证、最坏情况和固定回归基准见 [PQ 改进说明](ANN_IMPROVEMENT.md)。

## 二维可视化

### `GET /api/visualization/embedding`

查询参数：

- `method`：`umap` 或 `pca`，默认 `umap`；
- `max_points`：抽样上限，受服务端配置限制；
- `include_ids`：最多 101 个逗号分隔细胞编号，保证查询点和结果点进入响应。

同一数据集、方法和抽样上限使用确定性缓存。大数据集先稳定抽样，再将未抽到的指定细胞变换到同一坐标空间。

## 历史

### `GET /api/history/queries?limit=20`

普通用户只看到自己的查询；管理员看到全局查询。`limit` 为 1–100。

### `GET /api/history/evaluations?limit=10`

权限和限制同查询历史，返回评测请求与结果快照。

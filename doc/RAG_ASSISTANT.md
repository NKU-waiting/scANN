# RAG 单细胞分析助手

## 1. 能力与边界

助手把自然语言问题转换成服务器可验证的检索计划，先从用户明确选择的受管理数据集中检索真实证据，再生成带引用的回答。它支持三种计划：

| 计划 | 触发方式 | 检索行为 |
| --- | --- | --- |
| `similar_to_cell` | 问题包含唯一细胞名、`数据集名/细胞名`，或显式提交数据集 ID 与本地编号 | 在选定数据范围内查找该细胞的精确 Top-K |
| `cell_type_representatives` | 问题或结构化字段包含已知 `cell_type` | 计算匹配类型的向量中心，并返回最靠近中心的代表细胞 |
| `dataset_summary` | 没有可解析的查询细胞或类型 | 汇总规模、维度和有限的类型计数，不执行细胞相似度查询 |

自然语言解析器只负责受限实体与参数提取，不让外部模型生成 SQL、文件路径、权限判断或任意工具调用。数据集范围始终来自已认证请求中的 `dataset_ids`；问题中要求“忽略规则”或访问其他资源不会扩大范围。

回答是检索辅助，不是生物学定论、诊断或临床建议。类型代表是向量中心附近的检索结果，不等同于统计显著性、细胞注释或因果解释。

## 2. RAG 数据流

```text
自然语言问题 + 明确数据集范围
          │
          ▼
服务器校验：长度、K、度量、共享空间、资源上界
          │
          ▼
受限计划：相似细胞 / 类型代表 / 数据概览
          │
          ▼
精确向量检索 + 来源映射 + 数据集摘要
          │
          ├─ 未配置 provider：本地证据摘要
          │
          └─ 已配置 provider：严格 JSON Schema 的 Responses API
                                      │
                                      ▼
                            引用白名单二次校验
                                      │
                                      ▼
                       回答 + [D#]/[E#] + 检索证据表
```

- `[D#]` 引用数据集摘要；
- `[E#]` 引用具体检索细胞；
- 每个证据包含数据集 ID/名称、本地细胞 ID/名称、类型、数值和数值语义；
- 上下文、响应和历史均不包含原始向量；助手问题与回答当前不写入数据库历史。

## 3. 可选 OpenAI provider

未设置 provider 时系统仍可完成自然语言检索，并返回确定性的本地证据摘要。要启用 AI 生成，同时设置：

```text
OPENAI_API_KEY=<project API key>
SCANN_OPENAI_MODEL=<Responses API text model>
```

可选项：

```text
SCANN_OPENAI_BASE_URL=https://api.openai.com/v1
SCANN_OPENAI_TIMEOUT_SECONDS=30
SCANN_OPENAI_MAX_OUTPUT_TOKENS=800
```

模型应根据项目权限、成本和目标环境显式选择，不在代码中偷偷跟随浮动默认值。当前可用模型与 Responses 支持情况以 [OpenAI model guide](https://developers.openai.com/api/docs/models) 为准。

实现直接调用官方 `POST /v1/responses` 契约，使用 `instructions`、`input`、输出 token 上限与严格 JSON Schema；官方参考见 [Create a model response](https://developers.openai.com/api/reference/resources/responses/methods/create) 和 [Text generation](https://developers.openai.com/api/docs/guides/text)。请求固定使用 `store=false`，且不向模型开放工具。

## 4. 输出约束与失败语义

provider 必须返回：

```json
{
  "answer": "... [E1]",
  "citation_ids": ["E1"]
}
```

服务端仍会二次验证：

- 引用必须属于本次生成的 `[D#]`/`[E#]` 白名单；
- 正文中的引用集合必须与结构化引用集合一致；有细胞证据时至少引用一条 `[E#]`；
- 回答不能为空或超过服务端长度限制；
- provider 错误、超时、未完成响应、非法 JSON 或越权引用返回 `502`；
- provider 未配置不是错误，返回 `local_grounded` 与明确 warning；
- 参数、范围、维度或共享空间错误返回 `400`；不存在的数据集返回 `404`。

密钥只从服务端环境读取，不出现在状态接口、响应、日志或文档示例中。自动化测试使用 fake provider 和拦截的本地 HTTP 适配器，不访问真实外部服务。

## 5. 多数据集语义

选择多个数据集时仍必须填写共享向量空间标识并确认已经对齐。相同维度只证明矩阵可以计算距离，并不证明独立 PCA 基底可比。助手不会自动执行特征对齐、批次校正或跨模型映射。

资源上限由以下配置控制：

- `SCANN_MAX_FEDERATED_DATASETS`：单次最多选择的数据集；
- `SCANN_MAX_ASSISTANT_CELLS`：检索快照最多包含的细胞；
- `SCANN_MAX_ASSISTANT_EVIDENCE`：最大 Top-K/证据数；
- `SCANN_MAX_ASSISTANT_QUESTION_CHARS`：问题长度。

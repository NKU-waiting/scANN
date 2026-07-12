# scANN 结项交付说明

## 1. 交付结论

课程要求中的 Web 应用、用户模块、数据管理、索引构建/保存/加载/动态管理、细胞/向量 Top-K、条件检索、结果展示、性能评测均已实现。项目进一步完成了数据/索引指纹校验、查询与评测历史、UMAP/PCA 高亮、登录门禁、生产配置保护和自动化质量门。

功能状态以 [结项功能清单](FINAL_CHECKLIST.md) 为准，运行与验收以 [README](../README.md)、[用户手册](USER_GUIDE.md) 和 [测试说明](TESTING.md) 为准。

## 2. 需求追踪

| 课程要求 | 实现位置 | 验收证据 |
| --- | --- | --- |
| Web 应用 | Flask API + Vue SPA | 前端生产构建、登录后完整流程 |
| 用户注册/登录/管理员管理 | `backend/app/api/auth.py`、前端认证和用户管理 | 认证与权限回归测试 |
| 数据导入/读取/组织/校验 | 数据集 API、数据加载服务 | 三种格式与生命周期测试 |
| 精确与 ANN 索引 | NumPy Flat、FAISS Flat/IVF/HNSW/PQ | 全变体与 L2/Cosine/IP 测试 |
| 索引保存/加载/动态管理 | 索引持久化服务、文件清单、管理 UI | 往返、损坏、错配、级联测试 |
| 细胞/向量 Top-K | 查询 API 和检索服务 | 成功、边界和恶意输入测试 |
| 条件检索 | `cell_type` 子集精确回退 | 条件满足与数量保证测试 |
| 结果可视化 | 表格、条形图、类型分布、UMAP/PCA | 前端组件测试、投影 API 测试 |
| 查询耗时和索引状态 | 查询/状态响应与页面摘要 | API 回归测试 |
| 实验评估 | Flat ground truth、Recall@K、构建/查询耗时 | 评测服务和边界测试 |
| Git 开发过程 | 分阶段提交历史 | 每阶段独立 commit 与规定正文 |

## 3. 系统设计

### 3.1 逻辑分层

- 前端层：认证、数据集管理、索引管理、查询/评测、SVG 投影和历史组件。
- API 层：Blueprint 路由、JWT 门禁、请求解析、HTTP 状态映射。
- 服务层：数据集事务、索引事务、线程安全查询、评测、历史、投影缓存。
- 索引层：统一 `BaseIndex` 接口，NumPy 与 FAISS 实现。
- 持久化层：SQLAlchemy/SQLite 元信息，本地受控目录保存大文件。

### 3.2 一致性策略

- 新数据先保存为临时文件，完整解析后才原子改名发布。
- 数据集切换先构建新索引，成功后才替换内存状态；生命周期锁覆盖检查、数据库提交与发布。
- 索引构建失败不会修改当前算法、度量或索引对象。
- 索引加载先校验数据库记录、JSON 清单、数据集 ID/语义指纹、文件指纹、维度、规模和参数，再原子安装。
- 删除数据集时先把数据与关联索引改名为 tombstone；数据库提交失败可恢复文件，提交成功后清理 tombstone。
- 进程内使用可重入锁串行化活动数据集/索引的替换和查询。

### 3.3 条件检索保证

仅对 ANN 返回结果做一次后过滤，无法保证稀有类型能返回足量结果。当前实现先确定满足 `cell_type` 的候选集合，再在该子集上执行精确检索，因此在最坏情况下仍保证：

1. 每个返回项满足条件；
2. 返回数量等于 `min(K, 条件候选数)`；
3. 结果是条件候选集合内的精确 Top-K。

这牺牲了条件查询的部分速度，但给出了课程项目中更重要的可验证正确性保证。

## 4. 数据库设计

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| `users` | 用户和角色 | username、password_hash、role、created_at |
| `datasets` | 数据集元信息 | name、stored_path、format、规模、fingerprint、owner、active |
| `index_artifacts` | 索引元信息 | dataset_fingerprint、type、metric、parameters、paths、fingerprint、version |
| `query_logs` | 查询历史 | user、dataset、mode、cell_id、K、index、metric、filters、query_ms |
| `evaluation_logs` | 评测历史 | user、dataset、K、query_count、index_types、results |

密码使用 Werkzeug PBKDF2 哈希。原始查询向量、上传文件内容和索引本体不进入数据库。

## 5. 文件设计

- `data/uploads/`：系统生成随机文件名的上传副本；Git 忽略。
- `backend/indices/`：索引文件和同名 JSON 清单；Git 忽略。
- `backend/logs/`：轮转日志；Git 忽略。
- `backend/scann.db`：默认 SQLite；Git 忽略。

数据库只保存相对路径。文档、响应和清单不暴露开发机器绝对路径。

## 6. 接口与 UI 设计

接口采用资源化分组：`auth`、`datasets`、`index`、`search`、`eval`、`history`、`visualization`。完整请求/响应约束见 [API 文档](API.md)。

UI 为登录后的单页工作台，按“账户 → 数据 → 索引 → 查询 → 评测 → 历史”组织。耗时操作有独立状态；影响活动资源的操作互斥；表格在窄屏可横向滚动；主要错误使用 alert 语义；UMAP/PCA 使用原生 SVG 并附图例和点标题。

## 7. 安全与可靠性

- 所有业务接口必须登录，破坏性删除仅管理员可用。
- JWT 每次解析后查询数据库用户并校验登录版本，不信任 token 中的旧角色，也不会因 ID 复用复活旧 token。
- 生产环境拒绝开发密钥、默认管理员密码和 DEBUG。
- CORS 采用允许列表，上传和计算参数有上界。
- 路径解析拒绝绝对路径、`..` 和目录逃逸。
- NPY 禁止 pickle，所有向量必须二维、非空、有限且维度一致。
- 全局异常返回稳定 JSON 并回滚数据库 session；日志不记录认证凭据。

## 8. 测试与评估

后端采用 pytest，覆盖服务、所有索引变体、API、权限、文件生命周期、重启、历史与投影；前端采用 Vitest/jsdom，覆盖统一 API、登录门禁、数据集管理和 SVG 高亮。Ruff、ESLint 和生产构建作为静态质量门，GitHub Actions 自动执行。

详细矩阵、命令、隔离策略和评测口径见 [测试说明](TESTING.md)。不提交临时 smoke 脚本、输出、数据库、上传样本、索引、构建产物或运行日志。

## 9. 分阶段开发记录

1. `fix: harden retrieval and evaluation correctness`
2. `fix: enforce authenticated runtime safeguards`
3. `feat: add persistent multi-dataset lifecycle`
4. `feat: add dataset-bound index persistence`
5. `feat: complete management history and embedding UI`
6. `update: finalize reproducible project delivery`

每个提交正文包含 Changes、Verification、Scope，便于评审按阶段回溯。

## 10. 演示建议

建议 6–8 分钟流程：

1. 登录，说明普通用户/管理员权限差异。
2. 上传一个小型 CSV/NPY，展示格式校验和数据摘要。
3. 构建 Flat 与 HNSW，使用相同细胞执行查询和对比。
4. 添加 `cell_type` 条件，说明最坏情况保证。
5. 展示 Top-K 表格、类型分布和 UMAP 高亮。
6. 保存 HNSW，构建其他索引，再加载保存索引。
7. 执行多索引评测，展示 Recall@K/耗时。
8. 展示历史；切回 demo 后由管理员删除演示上传数据。

## 11. 项目组提交前必须补充

以下信息无法从代码库可靠推断，必须由项目组负责人填写并审核：

- [ ] 组员姓名、学号、角色和经全员确认的贡献度；
- [ ] GitHub 仓库与最终提交链接；
- [ ] 真实演示数据的来源、版本、许可、引用和脱敏说明；
- [ ] 课程要求的演示视频链接或现场演示安排；
- [ ] 若要公开分发，选择并由权利人确认项目许可证；
- [ ] 最终界面截图和评审环境的性能实测表。

这些项目属于外部授权或团队治理信息。仓库保留明确检查项，但不会编造姓名、许可、数据来源或性能数字。

## 12. 已知边界

- 活动数据集/索引是单进程共享状态，不支持多 worker 同步。
- SQLite 和本地文件系统适合课程演示，不面向高并发或多租户。
- 数据预处理限于读取已整理矩阵，不包含原始测序 QC 或复杂生物学分析。
- 条件检索当前实现 `cell_type`，尚未提供任意表达式过滤。
- UMAP 首次运行需要 JIT 编译，耗时受目标机器影响。

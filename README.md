# 旅游知识库助手

这是课程知识库项目的旅游行业特定版，保留原项目的 LangGraph、混合向量检索、HyDE、联网搜索、RRF、Reranker、SSE 流式输出和 MongoDB 历史记录能力。

## 能力范围

- 导入景点攻略、旅游线路、酒店信息、美食推荐和交通指南
- 保存城市、内容类型、景点/线路/酒店/餐厅名称、来源文件和章节等旅游元数据
- 支持普通 BGE-M3 混合向量检索和 HyDE 混合向量检索
- 支持联网搜索作为补充召回路线
- 使用 RRF 融合两路本地向量召回，再把联网结果交给 Reranker 统一排序
- 支持多轮对话、流式输出、图片引用和历史记录

## 查询流程

```text
旅游问题预处理
  -> 普通混合向量检索
  -> HyDE 混合向量检索
  -> 联网搜索
  -> 多路结果合并
  -> RRF
  -> Reranker
  -> 旅游答案和来源
```

三路检索仍然保留；当前 RRF 使用 `chunk_id` 融合两路 Milvus 结果，联网结果因为没有 Milvus 主键，在 Reranker 节点合并。这是对课程原有节点边界的保留。

联网搜索是补充召回路线；当 MCP 搜索服务暂时不可用时，系统会保留两路本地检索并继续生成答案。

## 启动前配置

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

Linux/macOS：

```bash
cp .env.example .env
```

然后在 `.env` 中填写自己的 API Key、Milvus、MongoDB、MinIO 和模型路径。不要把 `.env` 提交到 GitHub。

## 基础设施

Milvus、MongoDB 和 MinIO 可以使用老师提供的 Docker Compose 文件启动：

```bash
docker compose up -d
docker compose ps
```

如果 Python API 和 Docker 服务在同一台机器，`.env` 可以使用 `localhost`。如果 API 在 Windows、Docker 服务在 Linux，则把服务地址改为 Linux 主机地址，例如：

```dotenv
MILVUS_URL=http://<LINUX_HOST_IP>:19530
MONGO_URL=mongodb://<LINUX_HOST_IP>:27017
MINIO_ENDPOINT=<LINUX_HOST_IP>:9000
```

MinIO 的签名请求依赖服务器时间。Linux 主机需要确认时间同步正常；CentOS 7 可执行：

```bash
yum install -y chrony
systemctl enable --now chronyd
chronyc sources -v
chronyc tracking
```

确认 `Reach` 大于 `0` 且 `Leap status` 为 `Normal` 后，再进行文件导入测试。

安装依赖：

```bash
uv sync
```

启动导入服务：

```bash
uv run uvicorn web.api.import_service:app --host 127.0.0.1 --port 8000
```

启动查询服务：

```bash
uv run uvicorn web.api.query_service:app --host 127.0.0.1 --port 8001
```

两个服务需要分别在两个终端中启动。启动后检查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
```

两个接口都返回 `ok: true` 后，再打开页面。

页面地址：

- `http://127.0.0.1:8000/import.html`
- `http://127.0.0.1:8001/chat.html`

## 导入旅游资料

上传 Markdown 或 PDF 文件。Markdown 建议在正文前增加元数据小节，例如：

```markdown
# 成都景点推荐
## 元数据
- 内容类型：景点介绍
- 城市：成都
- 景点名称：成都景点推荐
- 主题：亲子、城市漫游
```

系统会把元数据复制到每个切片，并写入 `travel_chunks` 集合。首次导入时会创建新的旅游集合，不会写入课程示例的 `kb_chunks` 集合。

## 测试

当前仓库使用标准库 `unittest`：

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Linux/macOS：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

编译检查：

```bash
python -m compileall -q config processor utils web tests
```

测试覆盖旅游元数据解析、切片、向量文本上下文、旅游过滤表达式、导入路由和查询图节点注册。真实 BGE-M3、Milvus、DashScope、MCP 和 MongoDB 端到端调用需要在本地服务可用后再验证；本地端到端验证还应至少包含一次旅游资料导入、一次非流式查询、一次 SSE 查询和一次历史记录读取。

## GitHub 上传注意事项

- 提交 `.env.example`，不要提交 `.env`
- 不提交 `.venv`、模型缓存、临时文件和上传文件
- 不把课程资料目录整体复制到仓库；只保留项目代码和经授权的示例数据
- 旅游版作为主版本上传；老师原版可在本地另存为基线，不需要和旅游版混在同一个运行配置里

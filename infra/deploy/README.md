# DataForge 内部服务器部署

这一部署方式面向单台内部服务器，不包含多租户、网关计费或容器编排。DataForge 进程、SQLite 状态目录和 Milvus 由同一运维边界管理；LLM、Embedding 和 Reranker 继续调用现有内部 API。

## 1. 目录约定

```text
/opt/dataforge           DataForge 代码与 Python 虚拟环境
/opt/dataflow            DataFlow 代码
/srv/dataforge/state     SQLite、源文件、运行结果
/etc/dataforge           环境配置
```

状态目录必须持久化并允许 `dataforge` 用户写入。更新代码时不要删除 `/srv/dataforge/state` 或 `infra/milvus/volumes`。

## 2. 准备配置和构建

```bash
sudo install -d -o dataforge -g dataforge /srv/dataforge/state /etc/dataforge
sudo cp infra/deploy/dataforge.env.example /etc/dataforge/dataforge.env
sudo chown dataforge:dataforge /etc/dataforge/dataforge.env

# 修改路径和模型地址后，以 dataforge 用户执行
./infra/deploy/prepare.sh
```

如果环境变量中填写的是 API Key 环境变量名，还需要在同一配置文件中定义该变量的实际值。系统数据库只保存变量名，不保存密钥值。

## 3. 启动 Milvus 与 DataForge

Milvus 可以沿用项目中的单机 Compose：

```bash
docker compose -f infra/milvus/docker-compose.yml up -d
docker compose -f infra/milvus/docker-compose.yml ps
```

安装 systemd 服务：

```bash
sudo cp infra/deploy/dataforge.service.example /etc/systemd/system/dataforge.service
sudo systemctl daemon-reload
sudo systemctl enable --now dataforge
sudo systemctl status dataforge
```

默认监听内部网络的 `0.0.0.0:8000`。应通过服务器防火墙限制允许访问的内部网段；本系统暂不增加另一套登录和租户体系。

## 4. 部署检查

不调用模型的快速检查：

```bash
set -a
. /etc/dataforge/dataforge.env
set +a
uv run --extra dataflow --extra web --extra studio --extra indexing dataforge doctor
```

首次部署或修改模型配置后执行深度检查。它会真实调用 LLM、Embedding、Reranker 和 Milvus，并保存最近一次测试结果：

```bash
uv run --extra dataflow --extra web --extra studio --extra indexing dataforge doctor --deep
```

核心目录、SQLite 或任一深度依赖检查失败时命令返回非零退出码，可以直接用于发布脚本的门禁。

服务启动后执行 HTTP 冒烟验证：

```bash
uv run --extra dataflow --extra web --extra studio --extra indexing \
  dataforge smoke --url http://127.0.0.1:8000
```

运维探针：

- `GET /api/liveness`：进程存活，正常返回 HTTP 200。
- `GET /api/readiness`：状态目录和 SQLite 可用时返回 HTTP 200；前端、DataFlow 或模型尚未测试会显示 `degraded`，但不会阻止原生核心流程。
- `GET /api/health`：当前业务对象和配置摘要。

## 5. 更新和回滚

更新前备份 `/srv/dataforge/state`，并确保 Milvus 数据卷有独立快照。停止服务、更新代码、重新运行 `prepare.sh`，再启动并执行 `doctor --deep` 与 `smoke`。应用、集合、检索方案和索引均按不可变版本保存，业务配置回滚应切换到历史发布版本，不直接修改历史记录。

# Lightweight TiDB CRUD Demo

一个极简的单页数据管理 Demo：Vue 3 + TypeScript 前端、FastAPI 后端和 TiDB 数据库。支持创建、关键词查询、删除；浏览器通过 SSE 接收数据变更通知并自动刷新列表。

## 端口约定

为避免与本机已运行的 Python Study 项目冲突，本项目使用以下端口：

| 服务 | 地址 |
| --- | --- |
| Vue 前端 | `http://127.0.0.1:8517` |
| FastAPI 后端 | `http://127.0.0.1:8800` |
| FastAPI 接口文档 | `http://127.0.0.1:8800/docs` |
| TiDB SQL | `127.0.0.1:4000` |
| TiDB Dashboard | `http://127.0.0.1:2379/dashboard` |

## 1. 启动 TiDB（Mac）

TiDB 本地开发会运行三个进程：TiDB（SQL 入口）、PD（集群协调）和 TiKV（物理数据存储）。TiUP 会自动下载和启动它们；它不是 Docker，但实现的集群组成相同。

首次使用时安装 TiUP：

```bash
curl --proto '=https' --tlsv1.2 -sSf https://tiup-mirrors.pingcap.com/install.sh | sh
source ~/.zshrc
tiup --version
```

在一个单独的终端启动本地单节点集群：

```bash
tiup playground
```

保持此终端运行。首次启动会下载组件，SQL 服务就绪后可在另一个终端检查：

```bash
mysql -h 127.0.0.1 -P 4000 -u root -e 'SELECT VERSION();'
mysql -h 127.0.0.1 -P 4000 -u root -e 'CREATE DATABASE IF NOT EXISTS demo_app CHARACTER SET utf8mb4;'
```

`demo_app` 是逻辑数据库，不是一个可手工管理的目录。TiKV 以内部格式保存物理数据，TiUP 默认在当前 Mac 用户的 `~/.tiup` 目录管理组件和运行数据。停止 `tiup playground` 后，按其终端提示清理开发集群数据；不要手工修改 TiKV 数据文件。

## 2. 启动后端

```bash
cd backend
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8800 --reload
```

后端启动时自动创建订单导入表。`DATABASE_URL` 是 SQLAlchemy 的连接地址，包含数据库驱动、TiDB 主机和端口、用户名及默认逻辑数据库；本地开发默认值为：

```text
mysql+aiomysql://root@127.0.0.1:4000/demo_app?charset=utf8mb4
```

健康检查：`curl http://127.0.0.1:8800/health`

## 3. 启动前端

新开一个终端：

```bash
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:8517`。

## 实时更新与扩展边界

`GET /api/events` 是标准 SSE 接口。订单成功写入后，后端向连接的浏览器广播 `database_changed` 事件，当前查询表自动刷新。

当前事件广播仅保存在单个 FastAPI 进程的内存中，适合本地单机 Demo。需要横向扩展、后台任务或跨实例同步时，以 Redis Streams / Pub/Sub 或消息队列承载事件；需要客户端也持续发送实时消息时采用 WebSocket。Pinia 是前端状态管理工具，只有页面状态复杂时才需要，与 SSE 和 Redis 不构成替代关系。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/events` | SSE 数据变更通知 |
| `GET` | `/api/order-import/template` | 下载固定订单导入模板 |
| `POST` | `/api/order-import` | 上传 `.xlsx` / `.xls` 并导入订单 |

## Excel 订单导入

页面的“下载模板”会生成一个固定规则的 Excel 文件。上传时，第一行表头和顺序必须完全为：`订单ID`、`客户名称`、`订单金额`、`下单日期`。系统按固定映射写入前端选定的 `order_imports` 或 `order_import_archive` 表中的 `order_id`、`customer_name`、`amount`、`order_date` 字段。前端只展示这两个字段结构兼容的写入目标；后端也会再次校验，不能通过伪造请求写入其他表。

校验规则：仅支持 `.xlsx` / `.xls`；单文件最大 5 MB；最多 500 条数据；不允许公式；订单 ID 仅允许字母、数字、下划线和连字符，且不可重复；客户名称最长 100 字；金额大于 0 且最多两位小数；日期必须是 Excel 日期或 `YYYY-MM-DD`。校验失败、数据库中订单 ID 重复或写库失败时，前端会显示具体原因；写入使用单个事务，失败时不会写入部分数据。

“TiDB 数据表查询”区域通过 `GET /api/tables` 显示当前数据库所有表，并通过 `GET /api/tables/{table_name}/rows` 读取选中表的前 100 行。查询表名必须来自后端返回的实际表列表。

订单导入表和订单导入归档表支持在页面多选删除。后端通过 `DELETE /api/tables/{table_name}/rows` 接收主键 ID 列表，并且只允许删除 `order_imports`、`order_import_archive` 两张订单表的数据。

若数据库此前已运行旧版本，请在 TiDB 启动后执行一次迁移。该命令会删除旧的 `items` 表，并将 `order_imports_archive` 重命名为 `order_import_archive`，然后确保两张订单导入表存在：

```bash
cd backend
source .venv/bin/activate
python -m scripts.migrate_import_tables
```

安装新增依赖后可运行解析测试：

```bash
cd backend
python -m unittest discover -s tests
```

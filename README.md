# Lightweight TiDB CRUD Demo

一个极简的订单数据管理 Demo：Vue 3 + TypeScript 前端、FastAPI 后端和 TiDB 数据库。B 端支持 Excel 导入、查询、新增、修改和删除；C 端以订单卡片浏览全部业务订单。浏览器通过 SSE 接收数据变更通知并自动刷新。

## 端口约定

为避免与本机已运行的 Python Study 项目冲突，本项目使用以下端口：

| 服务 | 地址 |
| --- | --- |
| B 端 Vue 前端 | `http://127.0.0.1:8517` |
| C 端 Vue 订单卡片浏览 | `http://127.0.0.1:8518/c.html` |
| FastAPI 后端 | `http://127.0.0.1:8800` |
| FastAPI 接口文档 | `http://127.0.0.1:8800/docs` |
| TiDB SQL | `127.0.0.1:4000` |
| TiDB Dashboard | `http://127.0.0.1:2379/dashboard` |

## 下次启动（推荐）

首次完成下面的安装配置后，B 端开发需要打开三个终端；需要 C 端订单浏览时再打开第四个终端。所有命令均在项目根目录运行：

```bash
bash scripts/start-tidb.sh
```

```bash
bash scripts/start-backend.sh
```

```bash
bash scripts/start-frontend.sh
```

```bash
bash scripts/start-frontend-c.sh
```

按 TiDB、后端、B 端前端、C 端前端的顺序启动。四个命令都需要保持运行；停止时在对应终端按 `Ctrl+C`。C 端仅做订单浏览，默认访问 `http://127.0.0.1:8518/c.html`。脚本默认使用 TiDB `v8.5.7` 与 `demo-app` 标签，后端会使用 `backend/.venv`，前端仅在 `node_modules` 不存在时执行 `npm ci`。

## 1. 启动 TiDB（Mac）

TiDB 本地开发会运行三个进程：TiDB（SQL 入口）、PD（集群协调）和 TiKV（物理数据存储）。TiUP 会自动下载和启动它们；它不是 Docker，但实现的集群组成相同。

首次使用时安装 TiUP：

```bash
curl --proto '=https' --tlsv1.2 -sSf https://tiup-mirrors.pingcap.com/install.sh | sh
source ~/.zshrc
tiup --version
```

在一个单独的终端、项目根目录启动本地单节点集群：

```bash
bash scripts/start-tidb.sh
```

保持此终端运行。启动脚本会同时确认 TiDB SQL 的 `4000` 端口和 TiKV 存储服务的 `20160` 端口；只有二者都就绪，才可启动后端。首次启动会下载组件，SQL 服务就绪后可在另一个终端检查：

```bash
mysql -h 127.0.0.1 -P 4000 -u root -e 'SELECT VERSION();'
mysql -h 127.0.0.1 -P 4000 -u root -e 'CREATE DATABASE IF NOT EXISTS demo_app CHARACTER SET utf8mb4;'
```

`demo_app` 是逻辑数据库，不是一个可手工管理的目录。TiKV 以内部格式保存物理数据，TiUP 默认在当前 Mac 用户的 `~/.tiup` 目录管理组件和运行数据。停止 `tiup playground` 后，按其终端提示清理开发集群数据；不要手工修改 TiKV 数据文件。

### TiKV 崩溃排查与恢复

若页面请求等待很久后显示 `Failed to fetch`，先检查 TiKV 是否仍在运行：

```bash
lsof -nP -iTCP:20160 -sTCP:LISTEN
```

没有 `tikv-server` 输出时，TiDB 即使仍监听 `4000` 也不能读写数据。当前启动脚本会在这种情况出现时停止不完整的本地集群并提示原因。已观察到的本机崩溃报告位于：

```text
~/Library/Logs/DiagnosticReports/tikv-server-*.ips
```

本项目观察到的崩溃属于 TiKV/RocksDB 后台压缩路径的原生 `SIGSEGV`，不是 Excel 导入逻辑，也不是内存耗尽。先完整停止 Playground 后重新运行 `bash scripts/start-tidb.sh`。若同一版本持续崩溃，先保留报告并在确认可丢弃本地 Demo 数据后，再按 TiUP 官方当前稳定补丁版本的迁移说明重建 Playground 数据；**普通启动不会也不应自动删除 `~/.tiup/data/demo-app`**。

可通过环境变量临时指定已经验证过的 TiDB 版本，默认版本不会被静默改变：

```bash
TIDB_VERSION=vX.Y.Z bash scripts/start-tidb.sh
```

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

访问 B 端：`http://127.0.0.1:8517`。

## 4. 启动 C 端订单浏览

新开一个终端，在项目根目录运行：

```bash
bash scripts/start-frontend-c.sh
```

访问 `http://127.0.0.1:8518/c.html`。C 端为只读页面，会从当前 TiDB 连接下所有业务数据库、所有兼容订单字段的数据表中汇总订单，并以卡片展示。页面不展示数据库名或表名；每张卡片依次显示订单 ID、固定图片、客户名称、金额和下单日期。可切换“按订单 ID 排序”或“按下单日期排序”，每页 100 张卡片；也可按订单 ID、订单金额或客户名称查询。B 端导入、新增、修改或删除后，C 端会通过 SSE 自动刷新当前页。

## 实时更新与扩展边界

`GET /api/events` 是标准 SSE 接口。订单成功写入后，后端向连接的浏览器广播 `database_changed` 事件，当前查询表自动刷新。

当前事件广播仅保存在单个 FastAPI 进程的内存中，适合本地单机 Demo。需要横向扩展、后台任务或跨实例同步时，以 Redis Streams / Pub/Sub 或消息队列承载事件；需要客户端也持续发送实时消息时采用 WebSocket。Pinia 是前端状态管理工具，只有页面状态复杂时才需要，与 SSE 和 Redis 不构成替代关系。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/events` | SSE 数据变更通知 |
| `GET` | `/api/order-import/template` | 下载固定订单导入模板 |
| `POST` | `/api/order-import` | 上传 `.xlsx` / `.xls` 并导入订单 |
| `GET` | `/api/databases` | 获取当前 TiDB 连接可见的数据库 |
| `GET` | `/api/databases/{database}/tables` | 获取指定数据库的数据表 |
| `POST` | `/api/databases/{database}/tables` | 在业务数据库中创建固定结构的订单导入表 |
| `GET` | `/api/databases/{database}/tables/{table}/rows` | 获取指定数据表的前 100 行 |
| `GET` | `/api/databases/{database}/tables/{table}/orders` | 获取 B 端指定订单表的分页数据 |
| `POST` | `/api/databases/{database}/tables/{table}/orders` | 新增订单；订单 ID 重复时返回替换确认 |
| `PATCH` | `/api/databases/{database}/tables/{table}/orders/{order_id}` | 修改订单业务字段，订单 ID 不变 |
| `DELETE` | `/api/databases/{database}/tables/{table}/orders` | 按订单 ID 删除一条或多条订单 |
| `GET` | `/api/orders` | C 端聚合订单卡片数据，支持分页、排序和订单业务字段查询 |

## Excel 订单导入

页面的“下载模板”会生成一个固定规则的 Excel 文件。上传时，前四列的第一行表头和顺序必须完全为：`订单ID`、`客户名称`、`订单金额`、`下单日期`。系统允许其后存在由 Excel/WPS 格式产生的空白列，但这些列的每个单元格都必须为空；额外列中出现任何数据时，会提示具体行和列。

B 端上传区域可选择业务数据库及其数据表。后端将表头映射到 `order_id`、`customer_name`、`amount`、`order_date` 后，先确认该表具有这四个字段，再写入选中的 `数据库.数据表`。所选数据库尚未有任何表时，B 端会提供新建表输入框；表名仅可使用字母、数字和下划线，且必须以字母或下划线开头。新建表采用固定订单导入结构，建成后可立即选中导入和查询。系统数据库不会显示在选择器中。

若目标表已有相同的 `order_id`，首次上传不会改动任何数据，B 端会显示“数据部分已经存在，是否要替换？”。选择“否”会取消本次上传；选择“是”会重新上传并重新校验同一个 Excel 文件。校验成功后，后端会在一个事务中更新当前匹配订单的客户名称、金额和下单日期，保留原有 `id` 和 `order_id`，再仅插入文件中的新增订单；校验或写库失败都不会改动旧数据。

校验规则：仅支持 `.xlsx` / `.xls`；单文件最大 5 MB；最多 500 条数据；不允许公式；订单 ID 仅允许字母、数字、下划线和连字符，且不可重复；客户名称最长 100 字；金额大于 0 且最多两位小数；日期必须是 Excel 日期或 `YYYY-MM-DD`。校验失败、数据库中订单 ID 重复或写库失败时，前端会显示具体原因；写入使用单个事务，失败时不会写入部分数据。

“TiDB 数据表查询”区域可选择业务数据库和数据表；对于含 `order_id`、`customer_name`、`amount`、`order_date` 的兼容订单表，每页显示 100 条并按 `order_id` 升序排列。用户可新增订单、修改单条订单或勾选多条删除，所有删除均先二次确认。新增和修改使用与 Excel 完全相同的后端校验规则；修改时订单 ID 为只读。新增时如订单 ID 已存在，页面会询问是否替换，确认后只更新客户名称、金额和下单日期，保留 `id` 和 `order_id`。订单查询结果仅展示“订单ID”“客户名称”“订单金额”“下单日期”四列；这是前端显示映射，不会修改后端字段或 TiDB 数据表。

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

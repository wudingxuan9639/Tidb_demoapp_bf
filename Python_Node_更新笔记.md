# Mac 上更新 Python 与 Node.js：操作笔记

> **适用场景**：使用 zsh、Homebrew、pyenv 和 nvm 管理本机开发环境。
>
> **本项目建议版本**：Python 3.12；Node.js 使用当前 LTS（长期支持）版本。

## 先理解：什么是“全局更新”

> **重点问题：这些操作可以在任何目录执行吗？**

可以分为两类：

- **全局环境操作**（安装 pyenv、nvm、设置默认 Python/Node）可以在任意目录执行。
- **项目操作**（创建 `.venv`、安装 `requirements.txt`、`npm install`）必须进入对应项目目录执行。

> **重点：不要替换 macOS 自带的 `/usr/bin/python3`。**
>
> pyenv 只改变当前用户终端中 `python3` 默认指向的版本，不修改 macOS 系统 Python。

---

## 一、更新 Python（pyenv）

### 1. 安装 pyenv

```bash
brew install pyenv  # 通过 Homebrew 安装 Python 版本管理工具 pyenv
```

> **重点问题：终端出现 `pyenv: command not found` 怎么办？**
>
> 这表示 pyenv 还没有安装，或安装后的配置还未加载。先执行上面的安装命令，再完成下一步配置。

Homebrew 可能会显示自动更新相关的提示，例如：

```text
Adjust how often this is run with $HOMEBREW_AUTO_UPDATE_SECS ...
```

这不是报错，安装通常已经完成，可以忽略。它只是在说明 Homebrew 的自动更新行为。

### 2. 配置 zsh 在每次打开终端时加载 pyenv

```bash
nano ~/.zshrc  # 使用 nano 编辑当前用户的 zsh 启动配置文件
```

在文件末尾加入：

```zsh
export PYENV_ROOT="$HOME/.pyenv"                       # pyenv 的安装目录
[[ -d "$PYENV_ROOT/bin" ]] && export PATH="$PYENV_ROOT/bin:$PATH"  # 将 pyenv 命令加入终端搜索路径
eval "$(pyenv init - zsh)"                              # 启动 pyenv 的 shell 接管逻辑
```

> **重点问题：这三行是把 pyenv 应用到整个 Mac 吗？**
>
> 它们只作用于**当前 macOS 用户的 zsh 终端**。不会修改 macOS 系统 Python，也不会影响其他 macOS 用户；它会让你在终端输入 `python3` 时优先使用 pyenv 管理的版本。

#### nano 的保存方法

> **重点问题：为什么按 `Ctrl + 0` 没有反应？**
>
> nano 保存使用的是 `Ctrl + O`，其中 `O` 是英文字母，不是数字零。

```text
Ctrl + O  # 保存（WriteOut）
Enter     # 确认保存文件名 ~/.zshrc
Ctrl + X  # 退出 nano
```

保存后立即让配置生效：

```bash
source ~/.zshrc  # 重新加载 ~/.zshrc，无需关闭终端
pyenv --version  # 验证 pyenv 已被终端识别
```

### 3. 处理 Oh My Zsh 的 autojump 提示（可选）

如果执行 `source ~/.zshrc` 后出现：

```text
[oh-my-zsh] autojump not found. Please install it first.
```

这不是 Python 或 pyenv 错误。`~/.zshrc` 启用了 Oh My Zsh 的 `autojump` 插件，但本机没有安装它。

> **重点问题：不安装 autojump 可以吗？**
>
> 可以。它与 Python、Node.js、TiDB 和当前 Demo 无关。

不想安装时，编辑配置：

```bash
nano ~/.zshrc  # 打开 zsh 配置文件
```

在 nano 中按 `Ctrl + W` 搜索 `autojump`，将插件配置中出现的 `autojump` 删除：

```zsh
plugins=(git autojump)  # 修改前：启用了 autojump 插件
plugins=(git)           # 修改后：移除 autojump 插件
```

保存退出后执行：

```bash
source ~/.zshrc  # 重新加载修改后的配置，提示应消失
```

如果希望保留该插件，也可以安装它：

```bash
brew install autojump  # 安装目录跳转辅助工具 autojump
```

### 4. 安装并设置 Python 3.12

```bash
pyenv install 3.12      # 下载、编译并安装最新的 Python 3.12 补丁版本
pyenv global 3.12       # 设置当前用户终端默认 Python 为 3.12
python3 --version       # 确认默认 Python 版本
which python3           # 确认 python3 来自 ~/.pyenv/shims，而不是系统目录
```

预期 `which python3` 类似：

```text
/Users/你的用户名/.pyenv/shims/python3
```

---

## 二、更新 Node.js（nvm）

Node.js 使用 nvm 管理，不需要删除旧版本 Node。

```bash
source ~/.zshrc  # 确保当前终端已加载 nvm 配置
nvm --version    # 验证 nvm 是否可用
```

安装、切换并设置当前 LTS 为默认版本：

```bash
nvm install --lts                    # 下载并安装当前 Node.js LTS 版本
nvm use --lts                        # 在当前终端立即切换到该 LTS 版本
nvm alias default "$(node --version)" # 让之后新开的终端默认使用当前 Node 版本
node --version                       # 验证 Node.js 版本
npm --version                        # 验证 npm 版本
which node                           # 确认 Node 来自 ~/.nvm/versions/node/... 
```

> **重点：`nvm` 不会删除旧 Node。**
>
> 旧项目若仍需要 Node 18，可进入旧项目目录后执行 `nvm use 18`。

---

## 三、虚拟环境 `.venv`

> **重点问题：终端提示符中的 `(.venv)` 是什么？**
>
> 它表示当前终端已激活 Python 虚拟环境。虚拟环境会隔离某个项目的 Python 包，避免不同项目相互影响。

关闭当前虚拟环境：

```bash
deactivate  # 退出当前已激活的 Python 虚拟环境；不会删除 .venv 文件夹
```

激活项目的虚拟环境：

```bash
source .venv/bin/activate  # 在当前终端激活当前目录下的 .venv
```

> **重点：切换 Python 主版本后，需要重建项目虚拟环境。**
>
> `.venv` 内部绑定了创建它时使用的 Python 解释器。Python 从旧版本切换到 3.12 后，不应继续复用旧 `.venv`。

---

## 四、让当前 TiDB Demo 使用新版本

### 后端：重建 Python 虚拟环境

```bash
cd /Users/liuchangsheng/Documents/Python_demo/backend  # 进入 FastAPI 后端目录
deactivate 2>/dev/null || true                          # 如已激活旧环境则退出；未激活时继续执行
rm -rf .venv                                            # 删除旧的项目专用虚拟环境
python3 -m venv .venv                                   # 使用 pyenv 管理的 Python 3.12 创建新虚拟环境
source .venv/bin/activate                               # 激活新虚拟环境
python --version                                        # 应显示 Python 3.12.x
pip install -r requirements.txt                         # 安装 FastAPI、SQLAlchemy、aiomysql 等后端依赖
cp .env.example .env                                    # 创建本地数据库连接配置文件（首次执行即可）
uvicorn app.main:app --host 127.0.0.1 --port 8800 --reload  # 启动后端；监听 8800，代码变更时自动重启
```

### 前端：用新 Node 安装依赖并启动

```bash
cd /Users/liuchangsheng/Documents/Python_demo/frontend  # 进入 Vue 前端目录
rm -rf node_modules package-lock.json                   # 清理可能由旧 Node 创建的前端依赖和锁文件
npm install                                              # 依据 package.json 下载 Vue、Vite、TypeScript 等依赖
npm run dev                                              # 启动 Vite 开发服务器，端口固定为 8517
```

访问地址：

```text
前端：http://127.0.0.1:8517
后端：http://127.0.0.1:8800
接口文档：http://127.0.0.1:8800/docs
```

---

## 五、版本更新对项目的影响

| 更新内容 | 对当前 Demo 的影响 | 是否需要重建项目依赖 |
| --- | --- | --- |
| pyenv 全局 Python 版本 | 不会改动系统 Python；后端应改用新版本 | 需要重建 `backend/.venv` |
| nvm 默认 Node 版本 | 不会删除旧 Node；前端改用新版本 | 建议重装 `frontend/node_modules` |
| TiDB | 与 Python、Node 更新独立 | 不需要重建 TiDB 数据 |

> **重点：旧项目可能依赖旧版本。**
>
> Python 项目可以在自己的目录执行 `pyenv local 3.7`（按项目实际版本调整）；Node 项目可以执行 `nvm use 18`。这类按项目切换不会改变其他目录的版本选择。

---

## 六、TiDB CRUD Demo：项目全流程复盘

### 1. 项目采用的轻量化架构

本项目提供“创建、查询、删除、数据实时刷新”功能：

| 层级 | 技术 | 作用 |
| --- | --- | --- |
| 前端 | Vue 3 + TypeScript + Vite | 展示数据、提交表单、查询和删除 |
| 后端 | FastAPI + SQLAlchemy + aiomysql | 提供 REST API，读写 TiDB |
| 数据库 | TiDB | 保存数据，兼容 MySQL 协议 |
| 实时更新 | SSE | 后端向浏览器通知“数据已变化”，前端重新查询列表 |

> **重点问题：SSE 是自定义 API，还是一项技术方案？**
>
> SSE（Server-Sent Events）是一项浏览器标准通信技术。项目中的 `/api/events` 是自定义的接口路径，但该接口返回的数据遵循 SSE 标准。浏览器通过原生 `EventSource` 接收服务端单向消息。

本项目的实时逻辑：

```text
用户创建或删除数据
        ↓
FastAPI 写入 TiDB
        ↓
FastAPI 通过 SSE 广播 items_changed
        ↓
Vue 页面重新调用 GET /api/items
        ↓
列表显示最新数据
```

> **重点问题：SSE 只适合小项目吗？**
>
> 不是。SSE 适合“服务端单向通知浏览器”的场景，例如通知、日志流、状态看板。当前 Demo 使用内存广播，适合单机单后端进程。若系统有多个后端实例，需要 Redis Pub/Sub、Redis Streams 或消息队列同步事件；若浏览器也要持续向服务端推送实时消息，例如聊天和协作编辑，则使用 WebSocket。Pinia 属于前端状态管理，与 SSE、WebSocket 和 Redis 不互相替代。

### 2. TiDB 的三个进程与 Docker 的区别

| 组件 | 作用 |
| --- | --- |
| TiDB | SQL 入口；FastAPI 通过 `127.0.0.1:4000` 连接它 |
| PD | 管理元数据和集群协调 |
| TiKV | 以内部格式保存实际数据 |

`tiup playground` 会在本机启动单节点 TiDB、PD 和 TiKV。Docker 只是另一种运行这些服务的方式：手写 Docker Compose 时，需要自行维护多个容器、网络和卷；TiUP 会自动完成这些开发环境配置。

> **重点：这套 TiDB 服务运行在当前 Mac 用户环境中，不属于某一个项目目录。**
>
> `CREATE DATABASE demo_app` 创建的是逻辑数据库，不会生成可手工维护的“数据库根目录”。TiKV 的物理文件由自身管理，开发时不要直接修改。TiUP 默认在 `~/.tiup` 管理组件和运行数据。

### 3. 安装并启动 TiDB

首次安装 TiUP：

```bash
curl --proto '=https' --tlsv1.2 -sSf https://tiup-mirrors.pingcap.com/install.sh | sh  # 下载并运行官方 TiUP 安装脚本
source ~/.zshrc                                                                         # 重新加载终端配置，让 tiup 命令生效
tiup --version                                                                          # 验证 TiUP 已安装
```

> **重点问题：`curl: (6) Could not resolve host: tiup-` 是什么原因？**
>
> 如果命令中只有 `https://tiup-`，说明 URL 被截断，终端会把 `tiup-` 当作域名。必须使用上面的完整 URL。若完整 URL 仍无法解析，则是网络或 DNS 无法访问该域名。

启动本地集群：

```bash
tiup playground  # 启动单节点 TiDB、PD 与 TiKV；保持该终端运行
```

> **重点问题：提示 `component(nightly) not installed` 怎么办？**
>
> 这表示运行了 nightly（开发版）模式但缺少 Prometheus nightly 组件。项目开发优先使用稳定版的 `tiup playground`。确实需要 nightly 时才执行：

```bash
tiup install prometheus:nightly  # 下载 nightly 版本所需的 Prometheus 组件
tiup playground nightly          # 以 nightly 模式启动 Playground
```

验证 TiDB、创建项目数据库：

```bash
mysql -h 127.0.0.1 -P 4000 -u root -e 'SELECT VERSION();'  # 连接 TiDB，查询版本，以确认服务可访问
mysql -h 127.0.0.1 -P 4000 -u root -e 'CREATE DATABASE IF NOT EXISTS demo_app CHARACTER SET utf8mb4;'  # 创建 demo_app；已存在不报错；utf8mb4 支持中文和 Emoji
```

### 4. 后端连接字符串的作用

项目的默认连接字符串：

```text
mysql+aiomysql://root@127.0.0.1:4000/demo_app?charset=utf8mb4
```

含义如下：

| 片段 | 作用 |
| --- | --- |
| `mysql+aiomysql` | SQLAlchemy 使用 MySQL/TiDB 方言和 aiomysql 异步驱动 |
| `root` | 数据库用户名 |
| `127.0.0.1:4000` | 本机 TiDB SQL 服务地址 |
| `demo_app` | 默认操作的逻辑数据库 |
| `charset=utf8mb4` | 使用完整 UTF-8 字符集 |

### 5. pip 安装失败：排查记录

#### 问题 A：FastAPI 找不到符合版本的包

出现如下错误时：

```text
ERROR: Could not find a version that satisfies the requirement fastapi>=0.115.0
```

先确认**当前虚拟环境实际使用的解释器与 pip**，不要只看系统全局 Python：

```bash
python3 --version        # 查看当前 python3 版本
python3 -m pip --version # 查看当前 python3 对应的 pip 路径和版本
```

本项目曾出现“全局 Python 已是 3.12，但 `backend/.venv` 实际仍是 Python 3.7”的情况。旧虚拟环境不会随全局 Python 自动升级，必须重建。

```bash
cd /Users/liuchangsheng/Documents/Python_demo/backend  # 进入后端目录
deactivate 2>/dev/null || true                          # 尝试退出旧虚拟环境；未激活时不阻断命令
mv .venv ".venv-backup-$(date +%Y%m%d%H%M%S)"           # 备份旧环境，而不是直接删除
python3 -m venv .venv                                   # 用当前默认 Python 创建新环境
source .venv/bin/activate                               # 激活新环境
python --version                                        # 必须确认这里显示 Python 3.12.x
```

#### 问题 B：pip 软件源或 DNS 不可用

本机曾配置阿里云镜像，且该镜像未返回符合要求的 FastAPI 版本；之后切换官方源仍遇到域名无法解析。先查看 pip 的配置：

```bash
python3 -m pip config list  # 显示 pip 当前配置的软件源等信息
```

优先安装命令：

```bash
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple  # 升级当前虚拟环境的 pip，并指定清华镜像
python -m pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt  # 忽略缓存，从镜像安装后端依赖
```

> **重点问题：官方 PyPI 和镜像都报 `nodename nor servname provided` 怎么办？**
>
> 这是 DNS/网络问题，不是 FastAPI 版本问题。可在“系统设置 → 网络 → 当前网络 → 详情 → DNS”添加可用 DNS，例如 `223.5.5.5`、`119.29.29.29`，重新连接网络后验证：

```bash
nslookup pypi.org  # 查询 pypi.org 是否能被当前 DNS 正确解析
```

#### 问题 C：找不到 `backend/requirements.txt`

> **重点：命令路径必须与当前目录匹配。**

若已经位于 `backend` 目录，使用：

```bash
python -m pip install -r requirements.txt  # 当前目录就是 backend，因此直接读取 requirements.txt
```

若位于项目根目录，使用：

```bash
python3 -m pip install -r backend/requirements.txt  # 从项目根目录指定后端依赖文件的相对路径
```

### 6. 前后端启动报错：排查记录

浏览器曾出现：

```text
Failed to load resource: 404 (Not Found)
:8800/api/items?keyword=: net::ERR_CONNECTION_TIMED_OUT
```

排查结论：

1. 后端没有监听 `8800`，原因是 SQLAlchemy 异步引擎依赖的 `greenlet` 未安装。
2. 前端实际运行在 `5173`，而项目约定端口为 `8517`；`5173` 还是另一个项目已在使用的端口。

`backend/requirements.txt` 已包含：

```text
greenlet>=3.0.0  # SQLAlchemy 异步引擎所需的协程桥接依赖
```

启动顺序和验证命令：

```bash
cd /Users/liuchangsheng/Documents/Python_demo/backend  # 进入后端目录
source .venv/bin/activate                               # 激活已安装依赖的 Python 虚拟环境
pip install -r requirements.txt                         # 确保包括 greenlet 在内的依赖已安装
uvicorn app.main:app --host 127.0.0.1 --port 8800 --reload  # 启动 FastAPI，固定使用 8800
```

```bash
curl http://127.0.0.1:8800/health  # 后端健康检查；预期返回 {"status":"ok"}
```

新开终端，再启动前端：

```bash
cd /Users/liuchangsheng/Documents/Python_demo/frontend  # 进入前端目录
npm run dev                                              # 启动 Vite；vite.config.ts 固定端口为 8517
```

项目访问地址：

```text
前端：http://127.0.0.1:8517
后端：http://127.0.0.1:8800
接口文档：http://127.0.0.1:8800/docs
TiDB SQL：127.0.0.1:4000
TiDB Dashboard：http://127.0.0.1:2379/dashboard
```

> **重点：不要因为 Vite 默认端口是 5173，就直接访问 5173。**
>
> 本项目的 `frontend/vite.config.ts` 将端口固定为 `8517`，并启用 `strictPort`。若 8517 被占用，Vite 会报错而不是自动切换端口；这样可以避免误连到另一个项目。

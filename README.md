# Speak 聊天室

[![tests](https://github.com/ZZx-zzx2014/speak/actions/workflows/ci.yml/badge.svg)](https://github.com/ZZx-zzx2014/speak/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-orange)](CHANGELOG.md)

一个基于 **Flask + Flask-SocketIO + SQLite** 的轻量级实时聊天室，包含用户注册、登录、权限管理与实时消息推送。

启动方式：`python app.py`

---

## 功能

| 模块 | 说明 |
| --- | --- |
| 用户系统 | 注册、登录、退出；密码使用 PBKDF2-SHA256 加盐哈希存储 |
| 权限管理 | 普通用户 / 管理员两种角色，管理员可查看并删除普通用户 |
| 实时聊天 | 公共聊天室，支持消息广播、在线人数、上下线提醒 |
| 消息历史 | 新加入的用户自动收到最近 50 条消息 |
| 安全防护 | CSRF 校验、登录与消息限流、会话固定防护、CSP 等安全响应头 |
| 界面 | 响应式布局，桌面端与移动端均可用；无前端框架、无构建步骤 |

---

## 快速开始

**环境要求：** Python 3.8 及以上。

```bash
# 1. 进入项目目录
cd speak

# 2. 创建并激活虚拟环境
python -m venv myenv
source myenv/bin/activate          # Windows PowerShell: myenv\Scripts\Activate.ps1

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动
python app.py
```

打开浏览器访问 **<http://127.0.0.1:5002>**。

> **Python 3.8 用户提示：** 新建虚拟环境自带的 pip 可能较旧（如 20.2.1），
> 建议先执行 `python -m pip install --upgrade pip` 再安装依赖。

### 初始管理员账户

| 场景 | 用户名 | 密码 |
| --- | --- | --- |
| 调试模式（`SPEAK_DEBUG=true`） | `root` | `root` |
| 生产模式（默认） | `root` | **随机生成**，仅在启动日志中打印一次 |
| 任意模式 | `SPEAK_ADMIN_USERNAME` | 由 `SPEAK_ADMIN_PASSWORD` 指定 |

**公开部署前请务必设置：**

```bash
export SPEAK_ADMIN_PASSWORD='你的强密码'
export SPEAK_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

```powershell
# Windows PowerShell
$env:SPEAK_ADMIN_PASSWORD = '你的强密码'
$env:SPEAK_SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python app.py
```

> `SPEAK_SECRET_KEY` 不设置也能启动：会自动生成随机密钥并保存到 `.secret_key`
> （已加入 `.gitignore`）。多实例部署时请改用环境变量共享同一密钥。

---

## 目录结构

```
speak/
├── app.py                  # 开发入口：python app.py
├── wsgi.py                 # 生产入口：gunicorn "wsgi:app"
├── pyproject.toml          # 打包与项目元数据
├── requirements.txt        # 运行依赖
├── .env.example            # 全部环境变量示例
├── speak/                  # 应用包
│   ├── __init__.py         # create_app 应用工厂、版本号
│   ├── config.py           # 集中配置（全部支持环境变量）
│   ├── db.py               # SQLite 连接管理、建表、迁移
│   ├── schema.sql          # 表结构
│   ├── security.py         # CSRF、权限装饰器、限流、安全响应头
│   ├── validators.py       # 用户名 / 密码 / 消息校验
│   ├── auth.py             # 注册 / 登录 / 退出
│   ├── admin.py            # 用户管理
│   ├── chat.py             # 首页 / 聊天页
│   ├── events.py           # Socket.IO 事件与聊天状态
│   ├── socketio_client.py  # 前端客户端版本自动匹配
│   ├── static/             # style.css、chat.js
│   └── templates/          # Jinja2 模板
└── tests/                  # 61 个自动化测试
```

---

## 配置项

全部通过环境变量配置，无需修改源码。完整示例见 [`.env.example`](.env.example)。

**核心**

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SPEAK_SECRET_KEY` | 自动生成 | 会话签名密钥；未设置时自动生成并持久化到 `.secret_key` |
| `SPEAK_DEBUG` | `false` | 调试模式 |
| `SPEAK_HOST` | `127.0.0.1` | 监听地址；局域网访问改为 `0.0.0.0` |
| `SPEAK_PORT` | `5002` | 监听端口 |
| `SPEAK_DATABASE` | `<项目根>/database.db` | SQLite 文件路径 |

**会话与 Cookie**

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SPEAK_COOKIE_SECURE` | `false` | 使用 HTTPS 时设为 `true` |
| `SPEAK_SESSION_HOURS` | `12` | 登录态有效期（小时） |
| `SPEAK_MAX_CONTENT_LENGTH` | `65536` | 请求体上限（字节），超限返回 413 |

**Socket.IO**

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SPEAK_SOCKETIO_ASYNC_MODE` | `threading` | `threading`（长轮询）/ `gevent` / `eventlet` |
| `SPEAK_SOCKETIO_PATH` | `socket.io` | 端点路径 |
| `SPEAK_SOCKETIO_CORS_ALLOWED_ORIGINS` | 空 | 留空即强制同源策略 |
| `SPEAK_SOCKETIO_CLIENT_VERSION` | 自动检测 | 强制指定前端客户端版本 |
| `SPEAK_SOCKETIO_CDN_BASES` | 自动选择 | 前端加载客户端的 CDN 地址模板 |

**聊天与限流**

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SPEAK_CHAT_MAX_MESSAGE_LENGTH` | `500` | 单条消息最大字符数 |
| `SPEAK_CHAT_HISTORY_SIZE` | `50` | 新用户可见的历史消息条数 |
| `SPEAK_CHAT_MESSAGES_PER_WINDOW` | `20` | 时间窗口内允许的消息数 |
| `SPEAK_CHAT_RATE_WINDOW_SECONDS` | `10` | 消息限流窗口（秒） |
| `SPEAK_LOGIN_MAX_ATTEMPTS` | `5` | 登录/注册失败次数上限 |
| `SPEAK_LOGIN_WINDOW_SECONDS` | `300` | 登录限流窗口（秒） |

**管理员**

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SPEAK_ADMIN_USERNAME` | `root` | 初始管理员用户名 |
| `SPEAK_ADMIN_PASSWORD` | 见上文 | 初始管理员密码 |

**人机验证（Cloudflare Turnstile，可选）**

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SPEAK_TURNSTILE_SITE_KEY` | 空 | 站点公钥；留空即关闭人机验证 |
| `SPEAK_TURNSTILE_SECRET_KEY` | 空 | 服务端密钥；两个 key 都填才生效 |
| `SPEAK_TURNSTILE_TIMEOUT` | `5` | 校验请求超时（秒） |

> **启用步骤：** 到 <https://dash.cloudflare.com/> → Turnstile → Add site，
> 拿到 Site Key 与 Secret Key 后设为上面两个环境变量并重启服务。
> 未配置时登录/注册表单不会出现验证组件，功能完全不受影响。
>
> 校验失败一律**拒绝**（fail-closed）：令牌缺失、Cloudflare 不可达、返回内容无法解析
> 都视为不通过。这样可防止通过屏蔽校验接口来绕过验证，代价是 Cloudflare 故障期间无法登录；
> 每次拒绝的原因都会写入日志。

**响应加固**

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SPEAK_SECURITY_HEADERS` | `true` | 是否附加安全响应头 |
| `SPEAK_CONTENT_SECURITY_POLICY` | 见 `config.py` | CSP 策略，默认禁止内联脚本 |

---

## 使用说明

1. 首页 → 「注册」，用户名 3–20 个字符（中文/字母/数字/下划线），密码至少 8 位并需二次确认。
2. 登录后进入 `/chat`，自动连接并加入房间，可看到在线人数与最近的历史消息。
3. 消息以纯文本渲染，不支持 HTML 或 Markdown；发送过于频繁会被限流。
4. 管理员访问 `/manage` 可查看与删除普通用户；管理员账户和当前登录账户不会被列出。
5. 右上角「退出登录」可清除会话。

---

## 实时通信协议

替换前端时可参考以下事件约定。

**客户端 → 服务端**

| 事件 | 载荷 | 说明 |
| --- | --- | --- |
| `join` | `{}` | 加入聊天室，服务端随后返回历史消息与在线人数 |
| `chat_message` | `{"msg": "文本"}` | 发送消息；超长或超频时仅向发送者返回提示 |

> 连接建立时会校验会话，未登录的连接直接拒绝。

**服务端 → 客户端**

| 事件 | 载荷 | 说明 |
| --- | --- | --- |
| `history` | `{"messages": [{"username", "msg", "ts"}, ...]}` | 仅发给刚加入的用户 |
| `chat_message` | `{"username": "张三", "msg": "你好", "ts": 1710000000.0}` | 广播给房间内所有用户 |
| `system_message` | `{"msg": "张三 加入了聊天室", "ts": ...}` | 上下线通知与个人错误提示 |
| `presence` | `{"count": 3}` | 房间当前在线人数 |

`ts` 为 Unix 时间戳（秒，浮点）。

---

## 安全

| 风险 | 处理方式 |
| --- | --- |
| 会话密钥 | 不写死在代码中；未配置时自动生成随机密钥并持久化 |
| 调试模式 | 默认关闭；监听地址默认仅本机 |
| CSRF | 所有写操作校验会话令牌（Socket.IO 端点单独豁免） |
| 会话固定 | 登录成功后重建会话 |
| XSS | 前端全部使用 `textContent`；服务端过滤控制字符；CSP 默认禁止内联脚本 |
| 暴力破解 | 登录/注册按「来源 IP + 用户名」滑动窗口限流 |
| 自动化注册 / 撞库 | 可选接入 Cloudflare Turnstile 人机验证，校验失败一律拒绝 |
| 消息洪泛 | 按用户名限制发送频率 |
| 越权删除 | 删除用户前校验目标是否存在、是否为管理员、是否为当前账户 |
| SQL 注入 | 全部使用参数化查询 |
| 用户枚举 | 用户名不存在时同样执行一次哈希校验 |
| 开放重定向 | 登录后的 `next` 参数仅允许站内相对路径 |

部署检查清单见 [SECURITY.md](SECURITY.md)。

---

## 测试

使用标准库 `unittest`，无需额外依赖：

```bash
python -m unittest discover -s tests -t . -v
```

共 **75 个测试**，覆盖 HTTP 层（认证、鉴权、CSRF、安全响应头、旧库迁移）、
Socket.IO 层（连接鉴权、广播、历史回放、限流）、Turnstile 人机验证与纯函数单元测试。

---

## 生产部署

内置服务器仅用于开发，生产环境请使用 WSGI 服务器：

```bash
# 长轮询模式
gunicorn -w 4 "wsgi:app"

# WebSocket 模式（gunicorn 的 gevent worker 会自动打补丁）
pip install gevent gevent-websocket
gunicorn -k gevent -w 1 "wsgi:app"
```

使用 `python app.py` 时如需 WebSocket：

```bash
pip install gevent gevent-websocket
export SPEAK_SOCKETIO_ASYNC_MODE=gevent   # 或 eventlet
python app.py
```

`app.py` 会在导入任何网络模块**之前**完成 monkey patch；若后端未安装则自动回退到
`threading` 并打印提示。

**注意事项**

1. 反向代理需放行 WebSocket 升级头 `Upgrade`、`Connection`。
2. **请使用单进程**：聊天历史与在线状态保存在进程内存中，多 worker 时互相独立。
   如需横向扩展，请将状态迁移到 Redis。
3. HTTPS 环境请设置 `SPEAK_COOKIE_SECURE=true`。
4. 请显式设置 `SPEAK_SECRET_KEY` 并妥善保管。

---

## 版本与依赖策略

依赖基准为 **2026-09-12** 的最新发布：

| 包 | 当前最新 | Python 3.8 上安装到的版本 |
| --- | --- | --- |
| Flask | 3.1.3 | 3.0.3 |
| Werkzeug | 3.1.8 | 3.0.6 |
| Flask-SocketIO | 5.6.1 | 5.6.1 |
| python-socketio | 5.16.4 | 5.16.4 |
| python-engineio | 4.14.0 | 4.14.0 |

Flask 3.1 / Werkzeug 3.1 要求 Python ≥ 3.9，因此 `requirements.txt` 用环境标记
让 Python 3.8 自动回退到 3.0.x，两个版本都能装成功。

> `python -m pip index versions flask` 在 Python 3.8 上只列出 ≤ 3.0.3，
> 这是 pip 按解释器版本过滤的结果，不是版本源过旧。

> `requirements.txt` **只使用 ASCII 字符**。旧版 pip（如 Python 3.8 虚拟环境自带的
> 20.2.1）会用系统区域编码（中文 Windows 上是 GBK）读取该文件，遇到中文注释会抛
> `UnicodeDecodeError` 导致安装失败。修改时请继续保持英文注释。

### Socket.IO 协议对应关系（重要）

服务端与浏览器客户端必须协议一致，否则聊天室会连不上：

| python-engineio | Engine.IO 协议 | 需要的浏览器客户端 |
| --- | --- | --- |
| 3.x | v3 | `socket.io-client` 2.x |
| 4.x | v4 | `socket.io-client` 4.x |

项目由 `speak/socketio_client.py` 在运行时读取已安装的 engineio 版本自动选择
（含对应的 CDN 文件路径），无需手动配置。

---

## 常见问题

**Q：聊天室一直显示「连接中…」或「连接失败」？**

1. 打开浏览器控制台看是否 CDN 加载失败；若网络访问不了默认镜像，用
   `SPEAK_SOCKETIO_CDN_BASES` 换成可访问的地址。
2. 设置 `SPEAK_SOCKETIO_ENGINEIO_LOGGER=true` 查看服务端握手日志。
3. 若经反向代理访问，确认已放行 WebSocket 的 `Upgrade` / `Connection` 头。

**Q：`pip install -r requirements.txt` 报 `UnicodeDecodeError`？**

旧版 pip 用 GBK 读取该文件。请先 `python -m pip install --upgrade pip`。
仓库中的 `requirements.txt` 本身已是纯 ASCII，不会触发该问题。

**Q：原来的 `database.db` 还能用吗？**

可以。表结构保持兼容，首次启动会自动补齐新增列。

**Q：多进程部署后聊天记录不一致？**

聊天历史与在线状态存在各 worker 进程内存中，请使用单 worker 或迁移到 Redis。

**Q：如何允许局域网访问？**

设置 `SPEAK_HOST=0.0.0.0`。内置开发服务器不适合直接暴露到公网。

**Q：删除用户的接口路径变了？**

由 `POST /delete_user/<id>` 改为 `POST /manage/users/<id>/delete`，并增加了目标校验。

---

## 已知限制

- 聊天历史与在线状态保存在进程内存中，多 worker 部署时互相独立。
- 限流器为进程内实现，多 worker 下限流阈值按进程独立计算。
- 聊天记录不落库，进程重启后历史消息清空。
- 仅一个公共聊天室，暂不支持多房间或私聊。
- 未提供修改密码 / 找回密码功能。

---

## 参与贡献

欢迎提交 Issue 与 Pull Request。开始前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)：
提交前请确保 `python -m unittest discover -s tests -t . -v` 全部通过，并为新功能补充测试。

安全漏洞请勿开公开 Issue，请通过
[Private vulnerability reporting](https://github.com/ZZx-zzx2014/speak/security/advisories/new) 反馈。

## 更新日志

各版本变更见 [CHANGELOG.md](CHANGELOG.md)。当前版本 **1.0.0**（2026-09-12）。

## 许可证

[MIT](LICENSE) © 2026 ZZx-zzx2014

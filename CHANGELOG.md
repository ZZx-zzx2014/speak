# Changelog

本文件记录项目的重要变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-09-12

首个正式发布版本。在保留原有功能与 `python app.py` 启动方式的前提下，对项目进行了
全面的重构与加固。

### 安全（修复原版本中存在的真实漏洞）

- 修复会话密钥硬编码 `'your_secret_key'` 导致可伪造任意会话（含管理员）的问题。
- 默认关闭 `debug`，监听地址默认改为 `127.0.0.1`（原版本在 `0.0.0.0` 上开启调试器）。
- 新增 CSRF 防护：所有写操作校验会话令牌（Socket.IO 端点单独豁免）。
- 修复越权删除：`/delete_user/<id>` 可直接删除管理员账户，现改为 `/manage/users/<id>/delete`
  并校验目标身份、限制 POST + CSRF。
- Socket.IO 连接新增登录校验，未登录连接直接拒绝。
- 登录成功后重建会话，防止会话固定攻击。
- 新增登录/注册限流与消息发送频率限制。
- 用户名不存在时执行等时哈希校验，避免账户枚举。
- 注册强制密码长度 ≥ 8 位并需二次确认；生产环境管理员密码随机生成。
- 新增 CSP 等安全响应头。
- `database.db`、`.secret_key` 等敏感文件加入 `.gitignore`。

### 修复

- **修正 Socket.IO 客户端版本不匹配**：原版本固定加载 `socket.io@4.0.0`，与部分依赖
  版本（Engine.IO v3）协议不一致会导致聊天室完全无法收发消息。现由
  `speak/socketio_client.py` 在运行时按已安装的 `python-engineio` 版本自动选择匹配的
  浏览器客户端，并支持多 CDN 镜像自动回退。
- 修复注册失败分支未关闭数据库连接导致的连接泄漏。
- 修复未登录用户触发 Socket.IO 处理器时 `session['username']` 抛 `KeyError`。
- 修复 `beforeunload` 事件不可靠导致离线状态残留的问题，改用服务端 `disconnect`。
- 为旧版本创建的 `database.db` 增加自动迁移（补充 `created_at` 列）。

### 新增

- 退出登录功能（`POST /logout`）。
- 新用户加入时回放最近 50 条历史消息。
- 在线人数、连接状态、消息时间戳显示。
- 400 / 404 / 500 友好错误页面。
- 移动端响应式界面与独立样式表。
- 59 个自动化测试（HTTP / Socket.IO / 单元测试），并提供 GitHub Actions 工作流。
- `pyproject.toml` 打包配置、`CHANGELOG.md`、`SECURITY.md`、`CONTRIBUTING.md`。

### 变更

- 单文件 `app.py` 重构为应用工厂 + Blueprint 分层结构（`speak/` 包）。
- 配置集中到 `speak/config.py`，全部支持环境变量覆盖。
- 数据库连接改为请求级 `flask.g` 管理，启用 WAL 模式。
- 表结构移至 `speak/schema.sql`，幂等建表。
- 日志改用标准 `logging`，替换原有的 `print`。
- `requirements.txt` 改为精确的版本区间；`eventlet` / `gevent` 改为可选依赖，
  并按 Python 版本自动选择可用的 Flask/Werkzeug 版本。

### 移除

- 仓库中提交的 `database.db`（包含密码哈希，且应在运行时生成）。

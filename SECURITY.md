# 安全策略

## 支持版本

安全修复只针对最新的 `main` 分支（当前版本见 `CHANGELOG.md`）。

## 报告漏洞

请**不要**通过公开 Issue 报告安全问题。请使用 GitHub 的
[Private vulnerability reporting](https://github.com/ZZx-zzx2014/speak/security/advisories/new)
私下提交，或在 Issue 中只说明「有安全问题，希望私下沟通」。

报告中请尽量包含：

- 受影响的版本或提交
- 复现步骤（请求示例、账号角色、配置）
- 影响范围（能否越权、能否读取他人数据、能否导致服务不可用）

## 部署前必读

本项目默认配置面向本地开发，公开部署前请至少确认：

1. **设置 `SPEAK_SECRET_KEY`**：未设置时会自动生成并持久化到 `.secret_key`；
   多实例部署必须通过环境变量共享同一密钥，否则会话无法互认。
2. **设置 `SPEAK_ADMIN_PASSWORD`**：否则生产模式会随机生成管理员密码，
   仅在启动日志中打印一次。
3. **不要使用内置开发服务器对公网提供服务**：请使用 gunicorn / uWSGI 等
   WSGI 服务器，并在前面放置反向代理（Nginx / Caddy）。
4. **启用 HTTPS 并设置 `SPEAK_COOKIE_SECURE=true`**。
5. **限制 `SPEAK_SOCKETIO_CORS_ALLOWED_ORIGINS`**：留空即强制同源策略
   （默认值），请勿为图方便设置为 `*`。
6. **保持 `SPEAK_DEBUG=false`**：调试模式会暴露 Werkzeug 调试器。

## 已知的安全设计边界

- 限流器与聊天历史保存在**进程内存**中。多 worker 部署时每个进程独立计数，
  横向扩展请改用 Redis 或在前置反向代理上做限流。
- 数据库为 SQLite 单文件，适合中小规模部署；高并发场景建议替换为 PostgreSQL 等。

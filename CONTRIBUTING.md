# 贡献指南

感谢你愿意改进这个项目。以下是最小必要约定。

## 开发环境

```bash
git clone https://github.com/ZZx-zzx2014/speak.git
cd speak
python -m venv myenv
source myenv/bin/activate        # Windows: myenv\Scripts\activate
pip install -r requirements.txt
python app.py                    # http://127.0.0.1:5002
```

## 运行测试

测试使用 Python 标准库 `unittest`，无需额外依赖：

```bash
python -m unittest discover -s tests -t . -v
```

提交前请确保全部测试通过。新增功能请同时补充对应测试。

## 代码风格

- 遵循 [PEP 8](https://peps.python.org/pep-0008/)，单行不超过 100 字符。
- 注释与文档字符串使用中文或英文均可，但与所在文件保持一致。
- 所有 SQL 必须使用参数化查询，禁止字符串拼接。
- 所有用户输入必须经过 `speak/validators.py` 校验。
- 涉及渲染的用户数据必须使用 `textContent`（前端）或 Jinja 自动转义（模板），
  禁止 `innerHTML` 与 `|safe`。

## 提交信息

使用简洁的祈使句，建议带上范围前缀：

```
auth: 修复登录限流在多 worker 下失效的问题
chat: 支持自定义聊天室房间名
docs: 补充生产部署说明
```

## 安全相关改动

若改动涉及认证、授权、会话或输入处理，请在 PR 描述中说明威胁场景与验证方式。
安全问题请勿直接开公开 Issue，参见 [SECURITY.md](SECURITY.md)。

## 许可

贡献的代码将按本项目的 [MIT 许可证](LICENSE) 发布。

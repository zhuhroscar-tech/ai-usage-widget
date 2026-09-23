# AI Usage — ChatGPT 和 Claude 用量菜单栏小工具

🌐 [English](README.md) · **[中文](README.zh.md)** · [Español](README.es.md)

![AI Usage 预览图](assets/banner.png)

一个常驻 macOS 菜单栏的小工具，实时显示你的 ChatGPT 和 Claude
订阅还剩多少用量、什么时候刷新。不需要 API Key，不需要用终端——
像登录其他普通 App 一样，用你自己的账号登录就行。

## 显示内容

- **Claude** — 5 小时会话用量百分比，以及距离下次刷新还有多久
- **ChatGPT** — 每周用量百分比，以及距离下次刷新还有多久
- 颜色状态点（🟢 余量充足 · 🟡 快用完了 · 🔴 几乎耗尽）

## 安装（不需要写代码）

1. 从 [Releases](../../releases/latest) 下载最新的 `AI Usage.dmg`。
2. 打开它，把 **AI Usage.app** 拖进「应用程序」文件夹。
3. 双击打开。macOS 会提示"无法验证开发者"（因为这个 App 没有经过
   苹果的公证签名）——只需**右键点击这个 App → 打开 → 打开**
   一次即可放行。这是打开任何未付费公证的独立开发者 App 的标准
   安全方式。
4. 看屏幕右上角的菜单栏，就能看到实时百分比。

## 连接你的账号

- **ChatGPT**：点击菜单栏图标 → **Sign in with ChatGPT** →
  浏览器会打开 OpenAI 官方登录页面 → 正常登录 → 完成。这个流程
  用的是 OpenAI 自家 Codex CLI 使用的同一套公开 OAuth 授权方式——
  你的密码只会被 OpenAI 看到，这个 App 完全接触不到。
- **Claude**：如果你电脑上已经装了 [Claude 桌面版](https://claude.ai/download)
  并且已登录，这个小工具会自动识别，不用你做任何操作。（这里
  故意没有做"Sign in with Claude"按钮——因为 Anthropic 的用户
  条款限制 Claude Code 的 OAuth 客户端只能用于 Claude Code/claude.ai
  本身，这个 App 选择尊重这个限制，而不是绕过它。）

## 隐私说明

这个 App 只会和 OpenAI、Anthropic 各自的官方服务器通信，用的是
你自己已经登录的会话。不会把任何数据发送到别的地方，也不会上传
给这个 App 的开发者。源代码完全公开——可以直接看 `providers/`
目录，了解每一次请求到底做了什么。

## 从源码构建

需要 Python 3.11 及以上版本。

```bash
python3 -m venv .venv
.venv/bin/pip install rumps pycryptodome requests certifi pyinstaller
.venv/bin/pyinstaller --noconfirm "AI Usage.spec"
open "dist/AI Usage.app"
```

或者不打包，直接运行：

```bash
.venv/bin/python app.py
```

## 技术原理

- **ChatGPT**：使用浏览器 OAuth（PKCE 授权码流程，本地回环
  `localhost:1455` 接收回调），对接 `auth.openai.com`，用的是
  Codex CLI 同款的公开 client ID。令牌保存在 `~/.codex/auth.json`
  （和 Codex CLI 用的是同一个文件），并会自动刷新。用量数据来自
  ChatGPT 自己的 `wham/usage` 接口——和 ChatGPT 官方界面显示的
  是同一份数据。
- **Claude**：读取 Claude 桌面版自己受 Keychain 保护的会话 Cookie
  （macOS 钥匙串条目 `"Claude Safe Storage"`），调用和 Claude 官方
  界面一样的私有用量接口。这个接口是非官方的，如果 Anthropic
  改动前端实现细节，可能会失效。

两个平台的接入方式都只是使用**你自己已经登录的会话**——这个 App
不知道、也不会存储你在任何一个平台的密码。

## 已知局限

- 没有经过苹果公证签名（见上面安装第 3 步的解决办法）。
- Claude 的支持依赖于本机已安装并登录 Claude 桌面版；ChatGPT
  支持可以独立通过浏览器登录使用。
- 两个用量接口都是非官方、私有的，OpenAI 和 Anthropic 都不保证
  其稳定性。

## 许可

仅供个人使用。与 OpenAI、Anthropic 官方无关。

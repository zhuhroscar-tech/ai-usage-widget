# AI Usage — menu bar widget for ChatGPT & Claude usage

A tiny always-on macOS menu bar widget that shows how much of your
ChatGPT and Claude subscription you've used, and when it resets.
No API keys, no terminal — sign in with your real account like any
other app.

![menu bar example](https://img.shields.io/badge/menu%20bar-%F0%9F%9F%A2%2012%25%20%F0%9F%9F%A1%2040%25-black)

## What it shows

- **Claude** — your 5-hour session usage % and time until it resets
- **ChatGPT** — your weekly usage % and time until it resets
- A color-coded glyph (🟢 plenty left · 🟡 getting low · 🔴 almost out)

## Install (no coding required)

1. Download the latest `AI Usage.dmg` from
   [Releases](../../releases/latest).
2. Open it, drag **AI Usage.app** into **Applications**.
3. Double-click to launch. macOS will warn it's from an unidentified
   developer (the app isn't Apple-notarized) — **right-click the app
   → Open → Open** once to allow it. This is the standard, safe way
   to open any indie Mac app that hasn't paid Apple for notarization.
4. Look at the menu bar (top-right of your screen) for the live
   percentages.

## Connecting your accounts

- **ChatGPT**: click the menu bar item → **Sign in with ChatGPT** →
  your browser opens OpenAI's own login page → log in normally →
  done. This uses the same public OAuth flow OpenAI's own Codex CLI
  uses — your password is only ever seen by OpenAI, never by this app.
- **Claude**: if you have the [Claude desktop app](https://claude.ai/download)
  installed and signed in, this widget detects it automatically.
  (There's no "Sign in with Claude" button here on purpose — Anthropic's
  Consumer Terms of Service restrict using Claude Code's OAuth client
  outside Claude Code/claude.ai, so this app respects that instead of
  routing around it.)

## Privacy

This app only talks to OpenAI's and Anthropic's own servers, using
your own login session. Nothing is sent anywhere else, and nothing is
uploaded to the developer of this app. Source is fully open — read
`providers/` to see exactly what each request does.

## Building from source

Requires Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install rumps pycryptodome requests certifi pyinstaller
.venv/bin/pyinstaller --noconfirm "AI Usage.spec"
open "dist/AI Usage.app"
```

Or run directly without packaging:

```bash
.venv/bin/python app.py
```

## How it works (technical notes)

- **ChatGPT**: browser OAuth (PKCE, loopback callback on
  `localhost:1455`) against `auth.openai.com`, using the same public
  client ID Codex CLI uses. Tokens are stored in `~/.codex/auth.json`
  (the same file Codex CLI itself uses) and refreshed automatically.
  Usage is read from ChatGPT's own `wham/usage` endpoint — the same
  data ChatGPT's own UI shows you.
- **Claude**: reads Claude.app's own Keychain-protected session cookie
  (macOS Keychain item `"Claude Safe Storage"`) to call the same
  private usage endpoint Claude.app's own UI uses. This is unofficial
  and could break if Anthropic changes their frontend internals.

Both integrations use **your own already-authenticated session** —
this app does not know or store your password for either provider.

## Known limitations

- Not Apple-notarized (see install step 3 above for the workaround).
- Claude support depends on Claude.app being installed and logged in;
  ChatGPT support works standalone via browser sign-in.
- Both usage endpoints are unofficial/private and not guaranteed
  stable by OpenAI or Anthropic.

## License

For personal use. Not affiliated with OpenAI or Anthropic.

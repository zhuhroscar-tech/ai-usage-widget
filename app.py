"""Token Telescope — a macOS menu bar widget showing live ChatGPT Plus
and Claude Pro/Max subscription usage, pulled from each app's own
already-logged-in session. No API keys, no manual login.

Design: one status-glyph system (a single colored dot per provider,
color used only to encode remaining headroom — never decoration),
consistent spacing, plain numbers.
"""
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import rumps
from providers import claude_provider, chatgpt_provider, chatgpt_signin

APP_NAME = "Token Telescope"
REFRESH_INTERVAL_SECONDS = 90


def _resource_path(*parts) -> str:
    """Resolve a bundled resource whether running from source or as a
    frozen PyInstaller app (where data files live under sys._MEIPASS
    or next to the executable, not next to this .py file)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str(base.joinpath(*parts))


ICON_PATH = _resource_path("assets", "icon_alert.png")

# First-run guide: a small marker file, not the auth files, so re-installs
# or moving the app doesn't re-trigger it unless this support dir is wiped.
ONBOARD_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
ONBOARD_FLAG = ONBOARD_DIR / "onboarded"


def has_onboarded() -> bool:
    return ONBOARD_FLAG.exists()


def mark_onboarded() -> None:
    ONBOARD_DIR.mkdir(parents=True, exist_ok=True)
    ONBOARD_FLAG.touch()

# Status glyph system: one dot, three semantic colors. Never used decoratively.
DOT_OK = "\U0001F7E2"       # green  — plenty of headroom (used < 50%)
DOT_CAUTION = "\U0001F7E1"  # yellow — getting low (50-80%)
DOT_CRITICAL = "\U0001F534" # red    — nearly exhausted (> 80%)
DOT_UNKNOWN = "\u26AA"      # white  — no data / not signed in


def dot_for_used_percent(pct):
    if pct is None:
        return DOT_UNKNOWN
    if pct < 50:
        return DOT_OK
    if pct < 80:
        return DOT_CAUTION
    return DOT_CRITICAL


def fmt_countdown(target):
    if target is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    seconds = max(0, int((target - now).total_seconds()))
    if seconds <= 0:
        return "now"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def fmt_age(dt):
    if dt is None:
        return "never"
    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 5:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


def bar(percent_remaining, width=10):
    """Text progress bar of REMAINING headroom (not used)."""
    pct = max(0.0, min((percent_remaining or 0) / 100.0, 1.0))
    filled = int(round(pct * width))
    return "\u2588" * filled + "\u2591" * (width - filled)


class UsageApp(rumps.App):
    def __init__(self):
        super().__init__(name=APP_NAME, title="AI \u2013", icon=ICON_PATH, quit_button=None)
        self.menu = [
            rumps.MenuItem("claude_header", callback=None),
            rumps.MenuItem("claude_line1", callback=None),
            rumps.MenuItem("claude_line2", callback=None),
            None,
            rumps.MenuItem("chatgpt_header", callback=None),
            rumps.MenuItem("chatgpt_line1", callback=None),
            rumps.MenuItem("chatgpt_line2", callback=None),
            rumps.MenuItem("Sign in with ChatGPT", callback=self.sign_in_chatgpt_clicked),
            rumps.MenuItem("Sign out of ChatGPT", callback=self.sign_out_chatgpt_clicked),
            None,
            rumps.MenuItem("updated", callback=None),
            rumps.MenuItem("Refresh now", callback=self.refresh_clicked),
            rumps.MenuItem("Show Welcome Guide…", callback=self.show_welcome_clicked),
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]
        # AppKit auto-disables (and dims) any menu item with no action
        # selector — it doesn't matter that we call setEnabled_(True),
        # NSMenu overrides it on every display pass unless we turn that
        # behavior off. Our label-only rows (headers, usage lines,
        # "updated") aren't meant to be clickable, but they ARE meant
        # to be fully legible, not greyed out like a disabled button.
        top_menu = self.menu["Quit"]._menuitem.menu()
        top_menu.setAutoenablesItems_(False)
        for key in ("claude_header", "claude_line1", "claude_line2",
                    "chatgpt_header", "chatgpt_line1", "chatgpt_line2",
                    "updated"):
            self.menu[key]._menuitem.setEnabled_(True)
        self._last_fetch = None
        self._signing_in = False
        self.refresh(None)
        self.timer = rumps.Timer(self.refresh, REFRESH_INTERVAL_SECONDS)
        self.timer.start()

        if not has_onboarded():
            # Let the menu bar item + first refresh render before popping
            # the welcome alert, so it's not the very first thing a user
            # sees before anything else exists on screen.
            rumps.Timer(self._launch_welcome, 0.8).start()

    def _launch_welcome(self, timer):
        timer.stop()
        self.run_welcome_guide()

    def show_welcome_clicked(self, _sender):
        self.run_welcome_guide()

    def run_welcome_guide(self):
        rumps.alert(
            title=f"Welcome to {APP_NAME}",
            message=(
                "This little menu bar item shows how much of your ChatGPT "
                "and Claude subscription you've used, and when it resets.\n\n"
                "It updates automatically every 90 seconds — nothing to "
                "configure. Let's connect your accounts."
            ),
            ok="Continue",
        )

        # --- Step 1: ChatGPT ---
        if chatgpt_signin.is_signed_in():
            rumps.alert(
                title="ChatGPT — connected",
                message="You're already signed in to ChatGPT. Usage will show up in the menu bar shortly.",
                ok="Continue",
            )
        else:
            choice = rumps.alert(
                title="Connect ChatGPT",
                message=(
                    "Click Sign In to open your browser and log in to "
                    "ChatGPT normally — the same login page ChatGPT itself "
                    "uses. Your password is only ever seen by OpenAI."
                ),
                ok="Sign In",
                cancel="Skip for now",
            )
            if choice == 1:  # "ok" button
                self.sign_in_chatgpt_clicked(self.menu["Sign in with ChatGPT"])

        # --- Step 2: Claude ---
        claude_ok = claude_provider.claude_app_installed()
        if claude_ok:
            rumps.alert(
                title="Claude — detected",
                message="Found the Claude desktop app on this Mac. If you're signed in there, usage will show up automatically — nothing else to do.",
                ok="Continue",
            )
        else:
            choice = rumps.alert(
                title="Connect Claude",
                message=(
                    "Claude works a little differently: install the Claude "
                    "desktop app and sign in there once, and this widget "
                    "will detect it automatically. There's no separate "
                    "sign-in button here by design (Anthropic's terms "
                    "don't allow third-party apps to offer Claude login "
                    "directly)."
                ),
                ok="Open Claude Download Page",
                cancel="Skip for now",
            )
            if choice == 1:
                webbrowser.open("https://claude.ai/download")

        # --- Step 3: done ---
        rumps.alert(
            title="You're all set",
            message=(
                "Look for the colored numbers next to the clock, e.g. "
                "🟢12% 🟡53%. Click them anytime to see exact percentages, "
                "reset times, refresh manually, or sign out.\n\n"
                "🟢 plenty left · 🟡 getting low · 🔴 almost out\n\n"
                "You can replay this guide anytime from the menu → "
                "\"Show Welcome Guide…\"."
            ),
            ok="Got it",
        )
        mark_onboarded()
        self.refresh(None)

    def refresh_clicked(self, sender):
        self.refresh(sender)

    def sign_in_chatgpt_clicked(self, sender):
        if self._signing_in:
            return
        self._signing_in = True
        sender.title = "Opening browser…"

        def worker():
            result = chatgpt_signin.start_sign_in()
            self._signing_in = False

            def after():
                if not result.get("ok"):
                    rumps.alert(
                        title="ChatGPT sign-in failed",
                        message=result.get("error", "Unknown error"),
                    )
                self.menu["Sign in with ChatGPT"].title = "Sign in with ChatGPT"
                self.refresh(None)

            # rumps callbacks must touch the menu from the main thread;
            # schedule the follow-up instead of doing it on the worker thread.
            rumps.Timer(lambda _t: (after(), _t.stop()), 0.1).start()

        threading.Thread(target=worker, daemon=True).start()

    def sign_out_chatgpt_clicked(self, _sender):
        chatgpt_signin.sign_out()
        self.refresh(None)

    def refresh(self, _sender):
        try:
            claude = claude_provider.fetch_usage()
        except Exception as e:
            import traceback
            traceback.print_exc()
            claude = claude_provider.ClaudeUsage(error=f"crash: {e}")
        try:
            chatgpt = chatgpt_provider.fetch_usage()
        except Exception as e:
            import traceback
            traceback.print_exc()
            chatgpt = chatgpt_provider.ChatGPTUsage(error=f"crash: {e}")
        self._render(claude, chatgpt)

    def _render(self, claude, chatgpt):
        claude_worst = None
        if claude.available and claude.windows:
            claude_worst = max(w.percent for w in claude.windows if w.percent is not None)

        chatgpt_worst = None
        if chatgpt.available and chatgpt.windows:
            chatgpt_worst = max(w.percent for w in chatgpt.windows if w.percent is not None)

        c_dot = dot_for_used_percent(claude_worst)
        g_dot = dot_for_used_percent(chatgpt_worst)

        def pct_label(pct):
            return f"{int(round(pct))}%" if pct is not None else "\u2014"

        self.title = f"{c_dot}{pct_label(claude_worst)} {g_dot}{pct_label(chatgpt_worst)}"

        # --- Claude section ---
        self.menu["claude_header"].title = f"{c_dot} Claude"
        if claude.available and claude.windows:
            lines = []
            for w in claude.windows[:2]:
                remaining = 100 - w.percent if w.percent is not None else None
                lines.append(
                    f"  {w.label}: {pct_label(w.percent)} used  {bar(remaining)}  "
                    f"reset in {fmt_countdown(w.resets_at)}"
                )
            self.menu["claude_line1"].title = lines[0] if len(lines) > 0 else ""
            self.menu["claude_line2"].title = lines[1] if len(lines) > 1 else ""
        else:
            self.menu["claude_line1"].title = f"  {claude.error or 'No data'}"
            self.menu["claude_line2"].title = ""

        # --- ChatGPT section ---
        self.menu["chatgpt_header"].title = f"{g_dot} ChatGPT" + (f" ({chatgpt.plan_type})" if chatgpt.plan_type else "")
        if chatgpt.available and chatgpt.windows:
            lines = []
            for w in chatgpt.windows[:2]:
                remaining = 100 - w.percent if w.percent is not None else None
                lines.append(
                    f"  {w.label}: {pct_label(w.percent)} used  {bar(remaining)}  "
                    f"reset in {fmt_countdown(w.resets_at)}"
                )
            self.menu["chatgpt_line1"].title = lines[0] if len(lines) > 0 else ""
            self.menu["chatgpt_line2"].title = lines[1] if len(lines) > 1 else ""
        else:
            self.menu["chatgpt_line1"].title = f"  {chatgpt.error or 'No data'}"
            self.menu["chatgpt_line2"].title = ""

        signed_in = chatgpt_signin.is_signed_in()
        self.menu["Sign in with ChatGPT"].hidden = signed_in
        self.menu["Sign out of ChatGPT"].hidden = not signed_in

        self._last_fetch = datetime.now(timezone.utc)
        self.menu["updated"].title = f"Updated {fmt_age(self._last_fetch)} \u00b7 auto-refreshes every {REFRESH_INTERVAL_SECONDS}s"


if __name__ == "__main__":
    UsageApp().run()

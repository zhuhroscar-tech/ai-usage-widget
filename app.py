"""AI Usage Widget — a macOS menu bar widget showing live ChatGPT Plus
and Claude Pro/Max subscription usage, pulled from each app's own
already-logged-in session. No API keys, no manual login.

Design: one status-glyph system (a single colored dot per provider,
color used only to encode remaining headroom — never decoration),
consistent spacing, plain numbers.
"""
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import rumps
from providers import claude_provider, chatgpt_provider, chatgpt_signin

REFRESH_INTERVAL_SECONDS = 90

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
        super().__init__(name="AIUsage", title="AI \u2013", quit_button=None)
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
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]
        self._last_fetch = None
        self._signing_in = False
        self.refresh(None)
        self.timer = rumps.Timer(self.refresh, REFRESH_INTERVAL_SECONDS)
        self.timer.start()

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

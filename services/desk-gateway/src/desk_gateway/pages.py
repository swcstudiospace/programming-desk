"""The HTML pages the gateway serves: landing, consent, desk view sign-in, message."""

from __future__ import annotations

from html import escape

from desk_gateway.config import SEATS, Settings

_STYLE = """
:root{color-scheme:light dark;font-family:ui-sans-serif,system-ui,sans-serif}
body{max-width:38rem;margin:3rem auto;padding:0 1rem;line-height:1.5}
h1{font-size:1.4rem}code{font-family:ui-monospace,monospace;background:rgba(127,127,127,.15);padding:0 .3em;border-radius:3px}
label{display:block;margin:1rem 0 .3rem}input{width:100%;padding:.5rem;font-size:1rem}
button{padding:.55rem 1rem;font-size:1rem;margin-top:1rem;margin-right:.5rem}
.err{color:#b00020}.muted{opacity:.75;font-size:.9rem}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title><style>{_STYLE}</style></head><body>{body}</body></html>"


def landing_page(settings: Settings) -> str:
    seats = "".join(f"<li><code>/mcp/{escape(s)}</code></li>" for s in SEATS)
    return _page(
        "Programming Desk gateway",
        f"<h1>Programming Desk gateway</h1>"
        f"<p>One MCP endpoint per seat. Connect a Grok Bot with <strong>Add MCP Server</strong>, "
        f"URL <code>https://{escape(settings.public_host)}/mcp/&lt;seat&gt;</code>, authentication OAuth, "
        f"then enter that seat's passphrase on the consent page.</p><ul>{seats}</ul>"
        f"<p class='muted'>Health: <code>/health</code>. Intake: <code>POST /v1/intake</code> (origin token).</p>",
    )


def consent_page(*, request_id: str, client_name: str, client_id: str, redirect_host: str, error: str | None = None) -> str:
    err = "<p class='err'>That passphrase does not belong to any seat.</p>" if error == "bad_passphrase" else ""
    return _page(
        "Connect a seat",
        f"<h1>Connect a Programming Desk seat</h1>"
        f"<p><strong>{escape(client_name)}</strong> (<code>{escape(client_id)}</code>) wants to connect. "
        f"After approval it is sent back to <code>{escape(redirect_host)}</code>.</p>"
        f"<p>Enter the passphrase of the seat this Bot is. The passphrase decides the seat; the token "
        f"it mints works only on that seat's endpoint.</p>{err}"
        f"<form method='post' action='/oauth/consent'>"
        f"<input type='hidden' name='request' value='{escape(request_id)}'>"
        f"<label for='passphrase'>Seat passphrase</label>"
        f"<input id='passphrase' name='passphrase' type='password' autocomplete='off' required autofocus>"
        f"<button type='submit' name='action' value='approve'>Approve</button>"
        f"<button type='submit' name='action' value='deny'>Deny</button></form>",
    )


def view_login_page(error: str | None = None) -> str:
    if error == "throttled":
        err = "<p class='err'>Too many attempts. Wait ten minutes and try again.</p>"
    elif error:
        err = "<p class='err'>That passphrase is not the desk view passphrase.</p>"
    else:
        err = ""
    return _page(
        "Programming Desk",
        f"<h1>Programming Desk</h1>"
        f"<p>Enter the desk view passphrase to watch the desk.</p>{err}"
        f"<form method='post' action='/view/login'>"
        f"<label for='passphrase'>Desk view passphrase</label>"
        f"<input id='passphrase' name='passphrase' type='password' autocomplete='off' required autofocus>"
        f"<button type='submit'>Sign in</button></form>"
        f"<p class='muted'>Connecting a Grok Bot instead? See <code>/connect</code>.</p>",
    )


def message_page(title: str, text: str) -> str:
    return _page(title, f"<h1>{escape(title)}</h1><p>{escape(text)}</p>")

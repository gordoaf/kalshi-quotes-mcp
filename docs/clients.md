# Client setup

Use **stdio** when a desktop client starts the process. Use **Streamable HTTP**
when a client connects to a URL. Gemini's website needs a publicly reachable HTTPS
server; cloning a repository does not make localhost reachable from the cloud.

## ChatGPT desktop

Open **Settings → MCP servers → Add server**, select STDIO, and use:

- Command: `uvx` (or its absolute path).
- Arguments, separately: `--from`, `git+https://github.com/gordoaf/kalshi-quotes-mcp@v0.1.0`, `kalshi-quotes-mcp`.

For a checkout installed with pip, use the absolute path to
`.venv\Scripts\kalshi-quotes-mcp.exe` on Windows, or `.venv/bin/kalshi-quotes-mcp`
on macOS/Linux, with no arguments. Save and restart as the app requests.

For a hosted server choose Streamable HTTP and enter `https://YOUR-HOST/mcp`.
ChatGPT web uses a custom MCP plugin with the same remote URL, not local stdio.

[Official ChatGPT instructions](https://learn.chatgpt.com/docs/extend/mcp)

## Claude desktop

For local stdio, open Claude's developer settings and edit the MCP configuration.
The common Windows location is `%APPDATA%\Claude\claude_desktop_config.json`;
on macOS it is `~/Library/Application Support/Claude/claude_desktop_config.json`.
Merge this entry into the existing `mcpServers` object, preserving other settings:

```json
{
  "mcpServers": {
    "kalshi-quotes": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/gordoaf/kalshi-quotes-mcp@v0.1.0", "kalshi-quotes-mcp"]
    }
  }
}
```

Fully quit and reopen Claude. If it cannot find `uvx`, use its absolute path.
An installed executable in a checkout's `.venv` also works with no arguments;
escape backslashes as `\\` inside JSON strings.

For a remote server, use **Customize → Connectors** and add a custom web connector
with `https://YOUR-HOST/mcp`. This server's public-data tools need no sign-in.

[Official remote-connector instructions](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)

## Gemini website

Use **Settings → Connected Apps → Custom apps**, and enter `https://YOUR-HOST/mcp`.
Google currently requires a personal US account, age 18+, English, and History
enabled. If the option is missing, check the official requirements for your account.

[Official Gemini instructions](https://support.google.com/gemini/answer/17209137?hl=en)

## Host a shared endpoint

Run behind an HTTPS reverse proxy, hosting provider, or tunnel:

```sh
kalshi-quotes-mcp --transport streamable-http --host 0.0.0.0 --port 8000 --allowed-host quotes.example.com
```

Use the actual hostname, not the example. The proxy should forward `/mcp` and preserve
an allowed Host header. Repeat `--allowed-host` for additional exact names. Do not disable
DNS protection to bypass a wrong hostname. For custom local bind names, explicitly allow
the hostname and port that the client sends.

The server provides no authentication. Operators configure TLS, ingress rate limits,
and access restrictions if needed; any authentication layer must work with their clients.
An HTTPS tunnel to a desktop works only while the computer, tunnel, and server run.
An always-on host is more suitable for shared daily use. This repository does not deploy
or provision hosting automatically.

## Verify

1. Run `kalshi-quotes-mcp --check` to verify live API access.
2. Connect your client and confirm the four tools are available.
3. Ask it to call `list_markets` with `limit: 2`.
4. Ask for both returned tickers in one `get_quotes` call.
5. Confirm the answer reports bid/ask in cents and retrieval time.

Quotes can change between assistants' requests. For an evaluation at one fixed
point in time, share the same recorded response with all three assistants.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Command not found | Use an absolute executable path; restart the client after installing uv. |
| Terminal waits silently | Expected for stdio; an MCP client must communicate on stdin/stdout. |
| Remote client cannot reach localhost | Provide a public HTTPS endpoint. |
| Invalid Host or Origin | Check `--allowed-host` and proxy headers. |
| Rate limited | Reduce frequency and batch tickers; Kalshi limits still apply. |
| Missing market | Use the exact market ticker; archived markets may be absent. |
| Empty price | Report unavailable; inspect status or book if useful. |

Client menus and eligibility change; consult the linked official documentation.

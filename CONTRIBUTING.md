# Contributing

Focused fixes, tests, and documentation improvements are welcome. Keep this project
limited to public, read-only market data. Credentials and trading tools are out of scope.

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/), then:

```sh
uv sync --locked --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Use `uv lock` after intentional dependency changes. Keep `uv.lock` in the pull request.
Tests should be offline and deterministic; use `uv run kalshi-quotes-mcp --check`
for a separate live check. Test meaningful changes in parsing, validation, request
handling, or protocol behavior. Preserve decimal precision, units, and missing values.

Describe the problem, resulting behavior, and validation in each pull request. Update
setup instructions when behavior changes. Never submit credentials or private account
data in code, fixtures, issues, or screenshots. Contributions use the MIT License.

# Security

This application reads public market data. Do not supply Kalshi API keys or private
signing keys. Tools accept bounded tickers and filters, not arbitrary URLs or paths.
Upstream requests use a fixed HTTPS origin and only GET market endpoints. Redirects
are not followed. Titles and rules returned upstream are data, not instructions.

HTTP mode has no client authentication. Operators are responsible for HTTPS, access
restrictions when needed, ingress rate limits, resource limits, and dependency updates.
Keep DNS rebinding protection enabled and explicitly configure hostnames. Hostname
validation is not authentication. Public source code does not imply an obligation
to operate a public hosted service.

Use GitHub's **Report a vulnerability** option in the Security tab if available.
Otherwise open an issue requesting a private contact method without exploit details
or sensitive data. Coordinate disclosure before publishing an unfixed vulnerability.
Fixes target the latest release; no response-time guarantee is provided.

# Assets Management HQ

Personal, read-only investment decision-support system with a FastAPI backend
and React CEO headquarters.

## Security setup

The API fails closed unless `ASSET_API_TOKEN` is configured with at least 32
characters. Generate a token locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

For GitHub Codespaces, save the generated value as an account-specific
Codespaces Secret named `ASSET_API_TOKEN`, grant this repository access, and
restart the codespace. Never commit the token to this repository or place it in
a `VITE_` environment variable.

For official SEC filing checks, also add a Codespaces Secret named
`ASSET_SEC_USER_AGENT` with an identifying value such as
`Asset Agent your-email@example.com`. The dev container enables the New York
schedule automatically: low-cost scans at 08:30 and 12:30, followed by the
17:30 close check. Rebuild the container after changing Codespaces Secrets or
the dev-container schedule.

Keep forwarded ports `5173` and `8000` set to **Private** in the Codespaces
Ports panel. The application still requires its own Bearer token if a port is
accidentally exposed.

For local development, export the same environment variable before starting
the services:

```bash
export ASSET_API_TOKEN="your-generated-32-character-or-longer-token"
bash .devcontainer/start-ceo.sh
```

Open the React HQ on port `5173` and enter the token. The browser keeps it in
`sessionStorage`; using **CEO 로그아웃** removes it.

Run verification:

```bash
cd asset-agent
python -m pytest
cd ../asset-hq
npm run build
cd ..
bash .devcontainer/smoke-check.sh
```

## Safety boundary

The system reads portfolio data and produces decision support. Approval actions
record the CEO's decision only. They never place, modify, or cancel brokerage
orders.

See [`asset-agent/README.md`](asset-agent/README.md) for API and command-line
usage.

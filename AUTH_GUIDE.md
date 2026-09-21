# Last.fm authorization

The plugin needs three protected values, but only the first two are entered
manually:

- `api_key`: identifies the Last.fm API application.
- `shared_secret`: signs authenticated API requests.
- `session_key`: generated automatically after the user authorizes ONDA.

The official desktop flow is:

1. Call `auth.getToken` with the API key and a valid signature.
2. Open `https://www.last.fm/api/auth/?api_key=...&token=...` and approve access.
3. Call `auth.getSession` with that authorized token.
4. Store the returned session key in ONDA.

The authorization token expires and is single-use. The session key normally
remains valid until the user revokes application access.

Use **Conectar con Last.fm** in the plugin configuration to run these steps.
Never put any of these values in `plugin.json`, source control, screenshots or
bug reports.

# neurousers

Standalone auth service for Lidorub subdomains.

## Endpoints
- `GET /login?return_to=...` Telegram login page.
- `POST /auth` Login with Telegram payload.
- `POST /auth/refresh` Refresh access token via refresh cookie.
- `POST /auth/logout` Clear refresh cookie.
- `GET /auth/me` Current user by bearer access token.
- `GET /partners/` Current user partner tree (`referred_by` + `referrals`).
- `GET /auth/openrouter-settings` Get current user OpenRouter settings.
- `POST /auth/openrouter-settings` Update current user OpenRouter settings.
- `GET /auth/balance` Get current user balance (kopecks and rubles).
- `GET /auth/callback` Optional token-to-cookie bridge.
- `POST /admin/impersonate` Start impersonation (admin only).
- `POST /admin/stop-impersonate` Stop impersonation (admin only).
- `POST /admin/license` Extend license (admin only).
- `POST /admin/balance` Add balance (admin only).
- `POST /admin/create-user` Internal user upsert for cross-service sync (`X-Internal-Token`).

## Local start (docker)
1. `cd /home/mike/work/NEURO/users/docker/dev`
2. `docker compose up -d`
3. `docker compose exec api uv run aerich init-db`

For next schema changes:
1. `docker compose exec api uv run aerich migrate --name <msg>`
2. `docker compose exec api uv run aerich upgrade`

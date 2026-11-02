# Deployment

## 1. Prepare

```bash
git clone <repository-url> media-rank-api
cd media-rank-api
cp rank-api.env.example rank-api.env
chmod 600 rank-api.env
```

Edit `rank-api.env` and set `TMDB_API_KEY`. If TMDB is unreachable from the
server directly, set `TMDB_PROXY_URL` to an HTTP proxy. The optional
`RANK_API_KEY` enables API-key authentication.

## 2. Start

```bash
docker compose up -d --build
curl http://127.0.0.1:8891/health
```

The panel is served from `/`, API docs from `/docs`, and API routes from
`/api/v1/*`.

## 3. Publish through Nginx

Adapt `rank-api.inc` to your domain and include it inside the public TLS
`server {}` block:

```nginx
include /path/to/rank-api.inc;
```

The example assumes a reverse SSH tunnel exposing local port `18893` on the
public entry server.

## 4. Optional reverse tunnel

Copy `rank-api-tunnel.service`, replace `YOUR_ENTRY_HOST`, install it, and run:

```bash
systemctl daemon-reload
systemctl enable --now rank-api-tunnel
```

## 5. Add the small portal entry

The panel includes `portal-widget.js`. It can be injected into an authenticated
web portal with Nginx:

```nginx
sub_filter_once on;
sub_filter '</body>' '<script src="https://pan.qbb365.xyz/rank-api/portal-widget.js" defer></script></body>';
sub_filter_types text/html;
proxy_set_header Accept-Encoding "";
```

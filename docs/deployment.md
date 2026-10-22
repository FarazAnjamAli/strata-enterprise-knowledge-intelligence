# Deployment

## Single server with Docker Compose

```bash
./scripts/setup.sh            # or scripts\setup.ps1 on Windows
docker compose --profile local-llm up -d --build
docker compose ps
docker compose logs -f api worker
```

Only `web` publishes a port (`WEB_PORT`, default 3000). Put a TLS-terminating reverse proxy in front of it and set `COOKIE_SECURE=true`.

### Caddy example

```caddyfile
strata.example.com {
  encode zstd gzip
  reverse_proxy localhost:3000 {
    flush_interval -1   # keep chat answers streaming
  }
}
```

### Nginx example

```nginx
location / {
  proxy_pass http://127.0.0.1:3000;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_buffering off;          # Server-Sent Events
  proxy_read_timeout 300s;
  client_max_body_size 60m;     # MAX_FILE_SIZE_MB + headroom
}
```

## Using a native Ollama (Windows / macOS)

Install Ollama on the host, run `ollama pull llama3.1:8b`, start the stack without the `local-llm` profile and set:

```env
OLLAMA_URL=http://host.docker.internal:11434
```

## GPU

Uncomment the `deploy.resources` block on the `ollama` service (NVIDIA container toolkit required).

## Backups

```bash
# database
docker compose exec -T postgres pg_dump -U strata strata | gzip > strata-$(date +%F).sql.gz
# uploaded files (encrypted at rest; keep FILE_ENCRYPTION_KEY somewhere safe and separate)
docker run --rm -v strata_uploads:/data -v "$PWD":/out alpine tar czf /out/uploads-$(date +%F).tgz -C /data .
```

## Upgrading

```bash
git pull
docker compose up -d --build   # the migrate job applies new migrations first
```

## Rotating the file encryption key

1. Generate a new key and set `FILE_ENCRYPTION_KEY=<new>,<old>`.
2. Restart. New files use the new key and old files still decrypt.
3. Once the old files have been re-uploaded or re-encrypted, drop the old key.

## Health

- `GET /health`: liveness (used by the container healthcheck)
- `GET /health/ready`: Postgres and Redis reachability (503 when degraded)
- Admin console, Models tab: live tier health, failures and spend

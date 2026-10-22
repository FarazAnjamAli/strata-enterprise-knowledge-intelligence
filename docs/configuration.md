# Configuration

All settings are environment variables, read by `backend/app/config.py`. `.env.example` lists every one with its default. The most important ones:

## Required

| Variable | Notes |
|---|---|
| `POSTGRES_PASSWORD`, `REDIS_PASSWORD` | Use hex or URL-safe values: they are embedded in connection URLs. |
| `JWT_SECRET` | 32+ random characters. Startup fails if it is shorter. |
| `FILE_ENCRYPTION_KEY` | Fernet key. Required when `ENVIRONMENT=production`. Comma-separate keys, newest first, to rotate. |

`scripts/setup.sh` / `scripts/setup.ps1` generate all of them.

## LLM tiers

| Variable | Default | |
|---|---|---|
| `LLM_TIER_ORDER` | `local,free,paid` | Any order or subset, e.g. `free,local` |
| `LOCAL_LLM_ENABLED` | `true` | |
| `OLLAMA_URL` | `http://ollama:11434` | `http://host.docker.internal:11434` for a native install |
| `OLLAMA_MODEL` | `llama3.1:8b` | Any model you have pulled |
| `FREE_LLM_ENABLED` | `false` | |
| `FREE_LLM_BASE_URL` | Groq | Any OpenAI-compatible base URL |
| `FREE_LLM_API_KEY`, `FREE_LLM_MODEL` | | |
| `PAID_LLM_ENABLED` | `false` | |
| `PAID_LLM_PROVIDER` | `openai` | `openai`, `anthropic` or `openai_compatible` |
| `PAID_LLM_API_KEY`, `PAID_LLM_MODEL` | | |
| `PAID_LLM_INPUT_COST_PER_MTOK`, `PAID_LLM_OUTPUT_COST_PER_MTOK` | `0.15`, `0.60` | USD per million tokens, for cost tracking |
| `PAID_LLM_MONTHLY_BUDGET_USD` | `50` | The paid tier is skipped once reached |
| `PAID_LLM_REQUIRE_CONFIRMATION` | `true` | Ask the user before every paid call |
| `PAID_LLM_ALLOWED_ROLES` | empty | Empty means every role |
| `MASK_LOCAL_LLM` | `false` | External tiers are always masked |
| `LLM_CIRCUIT_COOLDOWN` | `30` | Seconds a failing tier is skipped |

### Example: Anthropic as the premium tier

```env
PAID_LLM_ENABLED=true
PAID_LLM_PROVIDER=anthropic
PAID_LLM_API_KEY=sk-ant-...
PAID_LLM_MODEL=claude-sonnet-4-5
PAID_LLM_INPUT_COST_PER_MTOK=3
PAID_LLM_OUTPUT_COST_PER_MTOK=15
```

### Example: OpenRouter free models as tier 2

```env
FREE_LLM_ENABLED=true
FREE_LLM_LABEL=OpenRouter
FREE_LLM_BASE_URL=https://openrouter.ai/api/v1
FREE_LLM_API_KEY=sk-or-...
FREE_LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

## Auth

| Variable | Default | |
|---|---|---|
| `AUTH_PROVIDER` | `local` | or `supabase` |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | `15` / `7` | |
| `PASSWORD_MIN_LENGTH` | `12` | Also needs three of: lower, upper, digit, symbol |
| `COOKIE_SECURE` | `false` | Set `true` once served over HTTPS |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` | | Creates the first admin when the user table is empty |

## Retrieval and files

`EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` (must match the model, and is fixed at the first migration), `ENABLE_RERANKING`, `TOP_K_RESULTS`, `CONTEXT_CHUNKS`, `MAX_FILE_SIZE_MB`, `ALLOWED_FILE_EXTENSIONS`, `ENABLE_OCR`, `OCR_LANGUAGE`.

## Security switches

`ENABLE_RBAC`, `ENABLE_RATE_LIMITING`, `ENABLE_AUDIT_LOGGING`, `ENABLE_FINANCIAL_MASKING`, `ENABLE_PROMPT_INJECTION_PROTECTION`, `FINANCIAL_MASKING_PATTERNS`, and `RATE_LIMIT_ADMIN` / `_DEPARTMENT_HEAD` / `_MANAGER` / `_MEMBER` / `_IP` (requests per minute).

## Optional

- `WEBHOOK_URL` / `WEBHOOK_SECRET`: events (`file.failed`, `access_request.created`, `access_request.decided`) are POSTed as JSON. With a secret, the body is signed in `X-Strata-Signature: sha256=<hmac>`.
- `IMAGE_GENERATION_ENABLED` / `GEMINI_API_KEY`: the `/image` diagram command. Off by default because the prompt leaves your network.

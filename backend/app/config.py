"""Application settings, loaded from the environment (or a local .env).

Every tunable lives here. Nothing else in the codebase reads os.environ.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

TierName = Literal["local", "free", "paid"]


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ------------------------------------------------------------ application
    app_name: str = "Strata"
    app_version: str = "2.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    # Departments offered in the admin UI. Free text is still accepted.
    departments: str = "Engineering,Finance,Human Resources,Legal,Marketing,Operations,Sales,Support"

    # ------------------------------------------------------------ database
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_pool_timeout: int = 30
    database_pool_recycle: int = 1800

    # ------------------------------------------------------------ redis / celery
    redis_url: str
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # ------------------------------------------------------------ auth
    # local   , users + bcrypt passwords live in Postgres, Strata issues JWTs
    #            (fully on-prem, the default)
    # supabase, Supabase Auth is the identity provider; Strata verifies its JWTs
    auth_provider: Literal["local", "supabase"] = "local"
    jwt_secret: str = Field(default="", min_length=0)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    password_min_length: int = 12
    password_hash_rounds: int = 12
    cookie_secure: bool = False  # set True behind HTTPS
    cookie_domain: str = ""
    # first-run admin (local auth only); ignored once any user exists
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_jwt_secret: str = ""

    cors_origins: str = "http://localhost:3000"

    # ------------------------------------------------------------ LLM tiers
    # Order the router walks. Default is on-prem first: the local model
    # answers, the free API covers outages, the paid API is the last resort.
    llm_tier_order: str = "local,free,paid"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    # seconds a tier is skipped after it fails (circuit breaker)
    llm_circuit_cooldown: int = 30
    # mask financial figures before text reaches the LOCAL model too
    # (external tiers are always masked)
    mask_local_llm: bool = False

    # Tier 1, local model (Ollama)
    local_llm_enabled: bool = True
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: int = 120
    ollama_num_ctx: int = 4096
    ollama_keep_alive: str = "30m"

    # Tier 2, free / low-cost hosted API (any OpenAI-compatible endpoint:
    # Groq, OpenRouter free models, Together, Cerebras, ...)
    free_llm_enabled: bool = False
    free_llm_label: str = "Groq"
    free_llm_base_url: str = "https://api.groq.com/openai/v1"
    free_llm_api_key: str = ""
    free_llm_model: str = "llama-3.3-70b-versatile"
    free_llm_timeout: int = 45

    # Tier 3, paid premium API
    paid_llm_enabled: bool = False
    paid_llm_provider: Literal["openai", "anthropic", "openai_compatible"] = "openai"
    paid_llm_base_url: str = "https://api.openai.com/v1"
    paid_llm_api_key: str = ""
    paid_llm_model: str = "gpt-4o-mini"
    paid_llm_timeout: int = 60
    # USD per 1M tokens, used for cost tracking and the budget guard
    paid_llm_input_cost_per_mtok: float = 0.15
    paid_llm_output_cost_per_mtok: float = 0.60
    paid_llm_monthly_budget_usd: float = 50.0
    # user must explicitly approve each paid call (cost control)
    paid_llm_require_confirmation: bool = True
    # roles allowed to use the paid tier at all (empty = everyone)
    paid_llm_allowed_roles: str = ""

    # ------------------------------------------------------------ embeddings / RAG
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    embedding_dimension: int = 768
    embedding_batch_size: int = 32
    embedding_cache_enabled: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    enable_reranking: bool = True
    rerank_top_k: int = 20
    top_k_results: int = 10
    context_chunks: int = 5
    context_chunk_chars: int = 1400

    # ------------------------------------------------------------ storage
    # Fernet key(s), comma-separated newest-first; empty = plaintext (dev only)
    file_encryption_key: str = ""
    upload_dir: str = "/data/uploads"
    max_file_size_mb: int = 50
    allowed_file_extensions: str = "pdf,docx,xlsx,csv,txt,md,json,xml,png,jpg,jpeg,mp4,mov,avi,mkv"

    # ------------------------------------------------------------ security
    enable_rbac: bool = True
    enable_rate_limiting: bool = True
    enable_audit_logging: bool = True
    enable_financial_masking: bool = True
    enable_prompt_injection_protection: bool = True
    financial_masking_patterns: str = "salary,revenue,cost,budget,profit,amount,price,payment"
    rate_limit_admin: int = 100
    rate_limit_department_head: int = 50
    rate_limit_manager: int = 30
    rate_limit_member: int = 10
    rate_limit_ip: int = 120

    # ------------------------------------------------------------ OCR
    enable_ocr: bool = True
    ocr_language: str = "eng"

    # ------------------------------------------------------------ optional features
    # Diagram generation (/image). Off by default: it sends the prompt to Google.
    image_generation_enabled: bool = False
    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-2.5-flash-image"
    gemini_timeout: int = 60

    # Outbound event webhook (n8n, Zapier, Slack relay, ...). Empty = off.
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_timeout: int = 10

    # ------------------------------------------------------------ validators
    def model_post_init(self, __context) -> None:
        # Celery defaults to the same Redis as everything else
        if not self.celery_broker_url:
            self.celery_broker_url = self.redis_url
        if not self.celery_result_backend:
            self.celery_result_backend = self.redis_url

    # ------------------------------------------------------------ derived
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return _csv(self.cors_origins)

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.lower() for e in _csv(self.allowed_file_extensions)}

    @property
    def masking_keywords(self) -> list[str]:
        return [k.lower() for k in _csv(self.financial_masking_patterns)]

    @property
    def department_list(self) -> list[str]:
        return _csv(self.departments)

    @property
    def tier_order(self) -> list[TierName]:
        valid = {"local", "free", "paid"}
        return [t for t in _csv(self.llm_tier_order) if t in valid]  # type: ignore[misc]

    @property
    def paid_roles(self) -> set[str]:
        return set(_csv(self.paid_llm_allowed_roles))

    def validate_runtime(self) -> list[str]:
        """Fatal misconfigurations, checked at startup."""
        problems = []
        if self.auth_provider == "local" and len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be at least 32 characters for local auth")
        if self.auth_provider == "supabase" and not self.supabase_url:
            problems.append("SUPABASE_URL is required when AUTH_PROVIDER=supabase")
        if self.is_production and not self.file_encryption_key:
            problems.append("FILE_ENCRYPTION_KEY is required in production")
        if not self.tier_order:
            problems.append("LLM_TIER_ORDER must list at least one of: local, free, paid")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

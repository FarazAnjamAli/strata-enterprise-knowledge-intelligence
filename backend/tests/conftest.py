"""Unit tests run without Postgres/Redis: settings come from env defaults
and anything touching a live service is monkeypatched."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://strata:strata@localhost:5432/strata_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6390/0")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-0123")
os.environ.setdefault("LOG_FORMAT", "text")

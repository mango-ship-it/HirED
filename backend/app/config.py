"""Central configuration. All secrets come from the environment / .env.

Never hardcode keys. `Settings` is validated once at import; missing required
keys surface as a clear startup error rather than a confusing 500 mid-request.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Sponsors (optional at import; validated per-feature at call time) ---
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")
    exa_api_key: str = Field(default="", alias="EXA_API_KEY")
    # Hard per-process daily cap on live Exa searches — protects a small budget. Once
    # hit, the roadmap layer short-circuits to the free deterministic search links.
    exa_daily_call_cap: int = Field(default=300, alias="EXA_DAILY_CALL_CAP")
    fal_api_key: str = Field(default="", alias="FAL_KEY")  # fal.ai — Pika video generation

    # --- Fetch.ai uAgent addresses (filled after agents start) ---
    resource_agent_address: str = Field(default="", alias="RESOURCE_AGENT_ADDRESS")  # deprecated, use coordinator
    resource_coordinator_address: str = Field(default="", alias="RESOURCE_COORDINATOR_ADDRESS")
    skills_resource_agent_address: str = Field(default="", alias="SKILLS_RESOURCE_AGENT_ADDRESS")
    experience_resource_agent_address: str = Field(default="", alias="EXPERIENCE_RESOURCE_AGENT_ADDRESS")
    education_resource_agent_address: str = Field(default="", alias="EDUCATION_RESOURCE_AGENT_ADDRESS")
    clarity_resource_agent_address: str = Field(default="", alias="CLARITY_RESOURCE_AGENT_ADDRESS")
    quantified_resource_agent_address: str = Field(default="", alias="QUANTIFIED_RESOURCE_AGENT_ADDRESS")
    benchmark_agent_address: str = Field(default="", alias="BENCHMARK_AGENT_ADDRESS")

    # --- Infra ---
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    # --- Models (default to the CHEAPEST capable model to conserve API credits;
    #     set CLAUDE_MODEL=claude-opus-4-8 for higher quality if budget allows) ---
    claude_model: str = Field(default="claude-haiku-4-5-20251001", alias="CLAUDE_MODEL")
    gen_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="GEN_MODEL"
    )  # optional report/slide polish; templated (free) path is the default

    # --- Scoring engine (pluggable; a teammate's scorer can drop in) ---
    # "deterministic" (default) or "custom" (app/services/custom_scorer.py). See
    # app/services/scoring_engine.py for how to add one.
    scorer: str = Field(default="deterministic", alias="SCORER")

    # --- TokenRouter — lightweight model gateway for 2AFC judging (OpenAI-compatible) ---
    token_router_api_key: str = Field(default="", alias="TOKEN_ROUTER_API_KEY")
    token_router_base_url: str = Field(default="https://api.tokenrouter.com/v1", alias="TOKEN_ROUTER_BASE_URL")
    token_router_model: str = Field(default="auto", alias="TOKEN_ROUTER_MODEL")

    # --- Sai data ingestion (Sai has no public API — we ingest its exported file) ---
    sai_data_path: str = Field(default="", alias="SAI_DATA_PATH")
    jd_data_path: str = Field(default="", alias="JD_DATA_PATH")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — import this, don't instantiate Settings directly."""
    return Settings()

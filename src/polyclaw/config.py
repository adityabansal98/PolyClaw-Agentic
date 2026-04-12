from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "POLYCLAW_"}

    # API base URLs
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"
    data_base_url: str = "https://data-api.polymarket.com"

    # Polygon chain ID
    chain_id: int = 137

    # Pagination / batching
    gamma_page_size: int = 100
    clob_batch_size: int = 50

    # Refresh intervals (seconds)
    market_refresh_interval: int = 600  # 10 minutes
    price_refresh_interval: int = 60  # 1 minute

    # Database
    db_path: str = "polyclaw.db"

    # Trading
    trading_mode: str = "paper"  # "paper" or "live"
    paper_db_path: str = "paper_trading.db"
    paper_starting_balance: float = 10_000.0
    db_backend: str = "sqlite"  # "sqlite" or "supabase"

    # Supabase (required when db_backend = "supabase")
    supabase_url: str = ""  # e.g. https://xxxxx.supabase.co
    supabase_key: str = ""  # anon/service_role key

    # Authentication (required for live trading only)
    private_key: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    api_passphrase: str | None = None


settings = Settings()

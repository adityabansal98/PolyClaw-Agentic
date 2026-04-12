from polyclaw.config import settings
from polyclaw.trading.interface import TraderInterface


def create_trader(mode: str | None = None) -> TraderInterface:
    """Create a trader based on the configured mode.

    Args:
        mode: "paper" or "live". Defaults to settings.trading_mode.
    """
    mode = mode or settings.trading_mode

    if mode == "paper":
        from polyclaw.trading.paper_trader import PaperTrader
        return PaperTrader(
            db_path=settings.paper_db_path,
            starting_balance=settings.paper_starting_balance,
        )
    elif mode == "live":
        from polyclaw.trading.live_trader import LiveTrader
        trader = LiveTrader()
        if settings.api_key and settings.api_secret and settings.api_passphrase:
            trader.set_creds(settings.api_key, settings.api_secret, settings.api_passphrase)
        else:
            trader.setup()
        return trader
    else:
        raise ValueError(f"Unknown trading mode: {mode!r}. Use 'paper' or 'live'.")

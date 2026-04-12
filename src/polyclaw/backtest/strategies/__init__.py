from polyclaw.backtest.strategy import Strategy
from polyclaw.backtest.strategies.momentum import MomentumStrategy
from polyclaw.backtest.strategies.mean_reversion import MeanReversionStrategy
from polyclaw.backtest.strategies.threshold import ThresholdStrategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
    "threshold": ThresholdStrategy,
}


def get_strategy(name: str) -> Strategy:
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
        raise ValueError(f"Unknown strategy: {name!r}. Available: {available}")
    return cls()


def register_strategy(name: str, cls: type[Strategy]) -> None:
    STRATEGY_REGISTRY[name] = cls

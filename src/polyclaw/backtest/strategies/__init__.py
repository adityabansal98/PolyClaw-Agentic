from polyclaw.backtest.strategies.fade_longshot import FadeLongshotStrategy
from polyclaw.backtest.strategies.kelly_sized import KellySizedStrategy
from polyclaw.backtest.strategies.mean_reversion import MeanReversionStrategy
from polyclaw.backtest.strategies.momentum import MomentumStrategy
from polyclaw.backtest.strategies.nothing_happens import NothingHappensStrategy
from polyclaw.backtest.strategies.pendulum import PendulumStrategy
from polyclaw.backtest.strategies.threshold import ThresholdStrategy
from polyclaw.backtest.strategy import Strategy

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
    "threshold": ThresholdStrategy,
    "kelly_sized": KellySizedStrategy,
    "fade_longshot": FadeLongshotStrategy,
    "pendulum": PendulumStrategy,
    "nothing_happens": NothingHappensStrategy,
}


def get_strategy(name: str) -> Strategy:
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
        raise ValueError(f"Unknown strategy: {name!r}. Available: {available}")
    return cls()


def register_strategy(name: str, cls: type[Strategy]) -> None:
    STRATEGY_REGISTRY[name] = cls

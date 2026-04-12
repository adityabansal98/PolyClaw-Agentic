from pydantic import BaseModel


class TradeRecord(BaseModel):
    timestamp: int
    token_id: str
    market_id: str
    market_question: str
    outcome: str
    side: str
    price: float
    shares: float
    cost: float
    fee: float
    reason: str = ""


class EquityPoint(BaseModel):
    timestamp: int
    cash: float
    position_value: float
    total_equity: float


class PerformanceMetrics(BaseModel):
    total_return_pct: float
    total_return_usd: float
    sharpe_ratio: float | None
    max_drawdown_pct: float
    max_drawdown_usd: float
    win_rate: float
    profit_factor: float | None
    avg_trade_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    best_trade_pnl: float
    worst_trade_pnl: float
    total_fees_paid: float


class BacktestResult(BaseModel):
    backtest_id: str
    strategy_name: str
    started_at: str
    finished_at: str
    starting_cash: float
    ending_cash: float
    ending_equity: float
    fee_bps: int
    fidelity: int
    markets: list[str]
    trades: list[TradeRecord]
    equity_curve: list[EquityPoint]
    metrics: PerformanceMetrics
    strategy_params: dict = {}

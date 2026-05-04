"""Demo mode progression: HW6 simple, HW7 experiments, HW8 scaled.

Verifies the demo data structure stays correct so the HW6/HW7/HW8 video demos
keep showing what they're supposed to show. If someone tweaks demoData.ts and
breaks the agent counts or the safety breaker setup, this file fails.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DATA = (REPO_ROOT / "frontend" / "src" / "lib" / "demoData.ts").read_text()


def test_hw6_has_one_agent():
    """[HW6] exactly 1 agent (the Dashboard Agent)."""
    assert "HW6_AGENTS" in DEMO_DATA
    section = DEMO_DATA.split("HW6_AGENTS")[1].split("HW6_APPROVALS")[0]
    assert section.count("agent_id:") == 1, "HW6 must have exactly 1 agent"
    assert "Dashboard Agent" in section


def test_hw7_has_six_agents_three_strategies():
    """[HW7] exactly 6 agents: 2 momentum, 2 mean_reversion, 2 kelly_sized."""
    section = DEMO_DATA.split("HW7_AGENTS")[1].split("HW7_EXPERIMENTS")[0]
    assert section.count("agent_id:") == 6, "HW7 must have exactly 6 agents"
    assert section.count("kelly_sized") == 2, "HW7 needs 2 kelly_sized agents"
    assert section.count("mean_reversion") == 2, "HW7 needs 2 mean_reversion agents"
    # momentum count: 2 agents, but 'momentum' string also appears in strategies array
    assert section.count("'momentum'") + section.count('"momentum"') >= 2


def test_hw7_kelly_alpha_has_142_sharpe():
    """[S2.result.sharpe] Kelly Alpha must show 1.42 Sharpe."""
    section = DEMO_DATA.split("HW7_AGENTS")[1].split("HW7_EXPERIMENTS")[0]
    # Find the Kelly Alpha entry
    assert "Kelly Alpha" in section
    # Sharpe 1.42 should be near it
    assert "1.42" in section, "Kelly Alpha must have Sharpe 1.42"


def test_hw7_has_three_experiments():
    """[HW7] 3 experiments: Strategy Comparison, Risk Gate, Backtest Queue."""
    section = DEMO_DATA.split("HW7_EXPERIMENTS")[1].split("HW7_BACKTEST_QUEUE")[0]
    assert "Experiment 1" in section
    assert "Experiment 2" in section
    assert "Experiment 3" in section


def test_hw7_risk_gate_log_has_correct_split():
    """[S2.result.risk] 3 rejected (external) + 3 filled (in-process) = 100% catch."""
    section = DEMO_DATA.split("HW7_RISK_GATE_LOG")[1].split("// ── HW8")[0]
    assert section.count("'REJECTED'") == 3, "Need exactly 3 REJECTED entries"
    assert section.count("'FILLED'") == 3, "Need exactly 3 FILLED entries"
    assert section.count("risk_gate.max_order_size") == 3


def test_hw7_backtest_queue_has_13_jobs():
    """[HW7 exp 3] 12 finished + 1 rejected (429) = 13 total entries."""
    section = DEMO_DATA.split("HW7_BACKTEST_QUEUE")[1].split("// ── HW8")[0]
    assert section.count("id: 'bt-") == 13, "Need 13 backtest jobs (12 + 13th rejected)"
    assert section.count("'finished'") == 12
    assert section.count("'failed'") == 1


def test_hw8_safety_breaker_paused_kelly_3x():
    """[S2.result.killswitch] Kelly-3x must be paused with 31% drawdown, 4.8s kill switch."""
    assert "kelly_3" in DEMO_DATA
    assert "Kelly-3x" in DEMO_DATA
    assert "PAUSED" in DEMO_DATA or "paused" in DEMO_DATA
    assert "0.31" in DEMO_DATA, "Kelly-3x must show 31% drawdown"
    # 4.8s kill switch is recorded in HW8_SAFETY_EVENTS
    assert "4.8" in DEMO_DATA or "4800" in DEMO_DATA, "Kill switch 4.8s must be present"


def test_hw8_walk_forward_flags_three_agents():
    """[S2.result.overfit] exactly 3 agents flagged for overfitting."""
    section = DEMO_DATA.split("HW8_WALK_FORWARD")[1].split("function generateMonteCarlo")[0]
    assert section.count("flagged: true") == 3, "Walk-forward must flag exactly 3 agents"
    assert section.count("flagged: false") == 2, "Walk-forward must show 2 healthy controls"


def test_hw8_monte_carlo_27_of_30_within_ci():
    """[S2.result.mc] Monte Carlo CI accuracy: 27/30 within = 3 outside."""
    # The deterministic generator hardcodes 3 outside CI (indices 5, 14, 22)
    assert "outsideCiIndices" in DEMO_DATA
    assert "[5, 14, 22]" in DEMO_DATA, "Monte Carlo must hardcode exactly 3 outside-CI agents"


def test_hw8_thirty_agent_breakdown():
    """[S1.stat.agents] 5 momentum + 3 kelly + 2 fade + 12 ext_http + 8 mcp = 30 agents."""
    # Loose check that the generator structure matches the slide
    assert "for (let i = 0; i < 5" in DEMO_DATA, "Need 5 momentum variants"
    assert "for (let i = 0; i < 3" in DEMO_DATA, "Need 3 Kelly variants"
    assert "for (let i = 0; i < 2" in DEMO_DATA, "Need 2 fade-longshot agents"
    assert "for (let i = 0; i < 12" in DEMO_DATA, "Need 12 external HTTP agents"
    assert "for (let i = 0; i < 8" in DEMO_DATA, "Need 8 MCP agents"


def test_hw8_season_finalized():
    """[HW8] Stress Test Season must be finalized."""
    section = DEMO_DATA.split("HW8_SEASON")[1].split("const HW8_WALK_FORWARD")[0]
    assert "Stress Test Season" in section
    assert "finalized" in section
    assert "starting_balance: 10000" in section
    assert "NBA only" in section

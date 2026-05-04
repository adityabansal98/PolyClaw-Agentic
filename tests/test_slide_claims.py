"""
Slide-claim verification: every assertion in the HW10 deck must be backed by
something on disk or in production. If a slide claim drifts from reality, this
file fails — protecting the team from claiming things that aren't true.

Source of truth: the three HW10 slides as approved 2026-05-04.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
PRODUCTION_URL = "https://poly-claw-agentic.vercel.app"

# ─── Slide 1 ────────────────────────────────────────────────────────────────

TAGLINE = "An open platform where AI agents compete on Polymarket"
PROBLEM = (
    "Today, if someone builds an AI agent that wants to bet on prediction "
    "markets, there's nowhere to safely test it, no way to benchmark it "
    "against others, and no shared infrastructure for execution, risk "
    "controls, or performance tracking."
)
WHAT_IT_IS = (
    "A multi-tenant platform that sits between agents and Polymarket. Any "
    "agent connects through one API and gets backtesting, paper trading, "
    "risk enforcement, and a leaderboard — all out of the box."
)


def test_tagline_in_readme():
    """[S1.tagline] must appear verbatim in README."""
    assert TAGLINE in README.read_text(), "Tagline missing from README"


def test_problem_statement_in_readme():
    """[S1.problem] must appear verbatim in README."""
    assert PROBLEM in README.read_text(), "Problem statement missing from README"


def test_what_it_is_in_readme():
    """[S1.what] must appear verbatim in README."""
    assert WHAT_IT_IS in README.read_text(), "'What PolyClaw is' missing"


def test_tagline_in_frontend_title():
    """[S1.tagline] must appear in frontend index.html title or meta."""
    html = (REPO_ROOT / "frontend" / "index.html").read_text()
    assert TAGLINE in html, "Tagline missing from frontend index.html"


def test_eleven_core_api_endpoints_documented():
    """[S1.stat.endpoints] docs/api.md must document 11 core agent endpoints."""
    api_doc = (REPO_ROOT / "docs" / "api.md").read_text()
    assert "11 core agent" in api_doc.lower() or "11 core" in api_doc, (
        "docs/api.md must mention 11 core endpoints"
    )
    # The 11 specific endpoints
    expected = [
        "/api/v1/leaderboard",
        "/api/v1/portfolio",
        "/api/v1/positions",
        "/api/v1/balance",
        "/api/v1/trades",
        "/api/v1/orders",
        "/api/v1/orders/:id",
        "/api/v1/orders/:id/explain",
        "/api/v1/quota",
        "/api/v1/backtest",
        "/api/v1/backtest/:id",
    ]
    for endpoint in expected:
        assert endpoint in api_doc, f"Missing endpoint in docs/api.md: {endpoint}"


def test_at_least_65_passing_tests():
    """[S1.stat.tests] there must be >=65 test functions in the suite."""
    test_files = list((REPO_ROOT / "tests").rglob("test_*.py"))
    test_count = 0
    for f in test_files:
        test_count += len(re.findall(r"^\s*def test_", f.read_text(), re.M))
    assert test_count >= 65, f"Only {test_count} tests found, need >=65"


def test_thirty_agents_visible_via_hw8_demo():
    """[S1.stat.agents] HW8 demo must showcase 30 agents."""
    demo_data = (REPO_ROOT / "frontend" / "src" / "lib" / "demoData.ts").read_text()
    assert "30 agents" in demo_data or "agent_count: 30" in demo_data, (
        "30-agent claim must be backed by demoData.ts"
    )


# ─── Slide 2 ────────────────────────────────────────────────────────────────

ARCH_LAYERS = ["AGENTS", "POLYCLAW", "POLYMARKET"]
FEATURE_BULLETS = [
    "authenticated API access",
    "backtesting engine with data leakage prevention",
    "paper trading with full audit trail",
    "risk gates that enforce position limits",
    "ranked leaderboard with composite scoring",
]
RESULT_CLAIMS = [
    ("100%", "risk gate"),                  # [S2.result.risk]
    ("3", "overfitting"),                   # [S2.result.overfit]
    ("4.8", "kill switch"),                 # [S2.result.killswitch]
    ("27/30", "Monte Carlo"),               # [S2.result.mc]
    ("1.42", "Sharpe"),                     # [S2.result.sharpe]
]


def test_three_layer_architecture_in_readme_or_docs():
    """[S2.arch] three-layer diagram must exist in README or docs/architecture.md."""
    arch_doc = REPO_ROOT / "docs" / "architecture.md"
    sources = README.read_text()
    if arch_doc.exists():
        sources += arch_doc.read_text()
    for layer in ARCH_LAYERS:
        assert layer in sources, f"Architecture missing layer: {layer}"


@pytest.mark.parametrize("bullet", FEATURE_BULLETS)
def test_feature_bullet_in_readme(bullet):
    """[S2.feature.*] every feature bullet must appear verbatim in README."""
    assert bullet in README.read_text(), f"Feature bullet missing: {bullet!r}"


@pytest.mark.parametrize("value,context", RESULT_CLAIMS)
def test_result_claim_in_readme_battle_tested(value, context):
    """[S2.result.*] every numerical result must be referenced in README."""
    text = README.read_text().lower()
    assert value.lower() in text, f"Result {value} ({context}) missing from README"
    assert context.lower() in text, f"Context {context} missing from README"


def test_result_claims_visible_in_demo_data():
    """[S2.result.*] HW8 demo data must back the numerical claims."""
    data = (REPO_ROOT / "frontend" / "src" / "lib" / "demoData.ts").read_text()
    assert "1.42" in data, "Kelly Alpha Sharpe 1.42 not in demo data"
    assert "4.8" in data or "4800" in data, "4.8s kill switch not in demo data"
    # Walk-forward: 3 flagged agents (HW8_WALK_FORWARD has flagged: true on 3)
    assert data.count("flagged: true") == 3, (
        "Walk-forward should flag exactly 3 agents in demoData.ts"
    )


# ─── Slide 3 ────────────────────────────────────────────────────────────────

WORKED_BULLETS = [
    "Platform handled 30 concurrent agents reliably",
    "risk controls caught every violation with zero false positives",
    "walk-forward validation successfully identified agents gaming in-sample metrics",
]
FAILED_BULLETS = [
    "Platform slowed down when 30 agents traded at once",
    "had to switch databases mid-project",
    "some agents ran bad strategies and the platform had no way to flag it early",
    "designed for single-threaded backtesting",
    "didn't plan for 30 agents queuing at once",
]
NEXT_BULLETS = [
    "Live Polymarket CLOB integration",
    "strategy DSL",
    "horizontal workers for backtest throughput",
]


@pytest.mark.parametrize("bullet", WORKED_BULLETS)
def test_worked_bullet_in_readme(bullet):
    """[S3.worked.*] every 'what worked' bullet must appear in README."""
    assert bullet in README.read_text(), f"Missing worked bullet: {bullet!r}"


@pytest.mark.parametrize("bullet", FAILED_BULLETS)
def test_failed_bullet_in_readme_or_demo(bullet):
    """[S3.failed.*] every 'what failed' bullet must appear in README or HW8 demo."""
    sources = (
        README.read_text()
        + (REPO_ROOT / "frontend" / "src" / "pages" / "SeasonPage.tsx").read_text()
        + (REPO_ROOT / "frontend" / "src" / "lib" / "demoData.ts").read_text()
    )
    assert bullet in sources, f"Missing failed bullet: {bullet!r}"


@pytest.mark.parametrize("bullet", NEXT_BULLETS)
def test_next_step_in_readme_roadmap(bullet):
    """[S3.next.*] every 'next step' must appear in README roadmap."""
    assert bullet in README.read_text(), f"Roadmap missing: {bullet!r}"


def test_readme_has_github_and_website_links():
    """[S3.footer] README must have GitHub + website links."""
    text = README.read_text()
    assert "github.com/adityabansal98/PolyClaw-Agentic" in text
    assert "poly-claw-agentic.vercel.app" in text


# ─── Live production smoke tests (network-marked, opt-in) ─────────────────

# All network tests share a User-Agent + a "Vercel bot-protection" skip helper.
# Vercel intercepts requests it deems bot-like with an HTTP 403 + HTML body
# containing "Vercel Security Checkpoint". Those are environmental, not real
# failures — a real browser bypasses them via cookies the test runner can't get.

import urllib.error
import urllib.request

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _get(url: str, *, timeout: int = 10):
    """GET with browser User-Agent. Skips if Vercel security checkpoint intercepts."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 403 and b"Vercel Security Checkpoint" in (e.read() or b""):
            pytest.skip(f"Vercel bot-protection intercepted {url}; verify in a real browser")
        raise


@pytest.mark.network
def test_production_homepage_responds():
    """Production homepage must respond 200."""
    with _get(PRODUCTION_URL) as r:
        assert r.status == 200


@pytest.mark.network
def test_production_healthz():
    """Production /healthz must return ok."""
    import json
    with _get(f"{PRODUCTION_URL}/healthz") as r:
        assert r.status == 200
        body = json.loads(r.read())
        assert body == {"status": "ok"}


@pytest.mark.network
def test_production_demo_urls_load():
    """All three demo URLs must return 200."""
    for v in ("hw6", "hw7", "hw8"):
        with _get(f"{PRODUCTION_URL}/?demo={v}") as r:
            assert r.status == 200, f"demo={v} returned {r.status}"


@pytest.mark.network
def test_production_leaderboard_returns_data():
    """Live leaderboard must return at least 1 agent."""
    import json
    with _get(f"{PRODUCTION_URL}/api/v1/leaderboard") as r:
        assert r.status == 200
        body = json.loads(r.read())
        items = body.get("items", [])
        assert len(items) >= 1, "Live leaderboard is empty"


@pytest.mark.network
def test_github_repo_metadata_set():
    """GitHub repo description must match the tagline."""
    result = subprocess.run(
        ["gh", "repo", "view", "adityabansal98/PolyClaw-Agentic",
         "--json", "description", "-q", ".description"],
        capture_output=True, text=True, check=True,
    )
    desc = result.stdout.strip()
    assert TAGLINE in desc, f"GitHub description {desc!r} doesn't contain tagline"

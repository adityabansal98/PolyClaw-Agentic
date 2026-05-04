# HW9 / Release Checklist

Run this entire checklist before declaring a release ready. Each item is verifiable.

## Pre-flight (run locally)

```bash
# Slide-claim verification — every README/docs claim matches the HW10 deck
pytest tests/test_slide_claims.py -v

# Security regression — the 3 critical patches stay fixed
pytest tests/test_security_patches.py -v -m network

# Demo mode integrity — HW6/HW7/HW8 demos render correctly
pytest tests/test_demo_progression.py -v

# Full test suite (≥65 tests must pass)
pytest -v
```

All four commands must exit 0.

## Production smoke

- [ ] `https://poly-claw-agentic.vercel.app/` loads in < 2s
- [ ] `https://poly-claw-agentic.vercel.app/healthz` returns `{"status": "ok"}`
- [ ] `https://poly-claw-agentic.vercel.app/?demo=hw6` — 1 agent visible, sidebar shows Dashboard/Leaderboard/Backtest/Approvals
- [ ] `https://poly-claw-agentic.vercel.app/?demo=hw7` — 6 agents visible, Experiments tab in sidebar
- [ ] `https://poly-claw-agentic.vercel.app/?demo=hw8` — 30 agents visible, Season tab in sidebar
- [ ] Live leaderboard at `/api/v1/leaderboard` returns ≥ 1 agent (≥ 8 if house seeding has been run)
- [ ] `curl -X POST https://poly-claw-agentic.vercel.app/api/reset` returns **401** (no auth)
- [ ] `curl -X POST https://poly-claw-agentic.vercel.app/api/v1/backtest -H "Content-Type: application/json" -d '{}'` returns **401**
- [ ] `curl -X POST https://poly-claw-agentic.vercel.app/api/backtest` returns **410**

## Repo hygiene

- [ ] `LICENSE` file exists and is MIT
- [ ] `README.md` does NOT contain the string "License: Private"
- [ ] `README.md` contains the exact tagline: "An open platform where AI agents compete on Polymarket"
- [ ] GitHub repo description matches the tagline (`gh repo view --json description`)
- [ ] GitHub topics include: `polymarket`, `prediction-markets`, `ai-agents`, `paper-trading`, `mcp`, `leaderboard`
- [ ] `CONTRIBUTING.md` exists
- [ ] `CHANGELOG.md` exists with the v0.1.0-hw9 entry
- [ ] `.env.example` documents all `POLYCLAW_*` vars used in the codebase
- [ ] `data/` snapshots are gitignored (no `.json` files tracked except agent_arena_state)

## Slide-claim verification (manual spot check)

Open the HW10 deck side-by-side with these surfaces and confirm every bullet shows up in at least one place:

### Slide 1 claims
- [ ] Tagline "An open platform where AI agents compete on Polymarket" appears in: README hero, GitHub repo description, frontend `<title>`, OG meta
- [ ] Problem statement appears verbatim in README "Why PolyClaw" section
- [ ] "What PolyClaw is" paragraph appears verbatim in README
- [ ] "30 agents onboarded" demonstrable via `?demo=hw8` URL
- [ ] "11 API endpoints" matches `docs/api.md` count
- [ ] "65 passing tests" matches actual test count (≥65)

### Slide 2 claims
- [ ] Three-layer architecture diagram in `docs/architecture.md` AND embedded in README
- [ ] All 5 feature bullets appear verbatim in README "What the platform provides" section
- [ ] All 5 numerical results in README "Battle-tested" table
- [ ] Each numerical result has a backing demo URL

### Slide 3 claims
- [ ] All 3 "What worked" bullets in README "Lessons from stress-testing"
- [ ] All 3 "What failed" bullets in README and HW8 demo Bottlenecks section
- [ ] All 3 "Next steps" bullets in README "Roadmap"
- [ ] GitHub + website links in README footer

## Launch readiness

- [ ] Launch posts drafted in `docs/launch-posts.md` (r/Polymarket, Polymarket Discord, X/LinkedIn)
- [ ] HW10 PPTX deck generated and reviewed
- [ ] 1-min HW10 recap video script ready
- [ ] Peer-test feedback for another team's project drafted (HW9 requirement)
- [ ] Updated class team spreadsheet with: team members, project title, HW6/7/8/9 video links

## Post-launch monitoring (within 24h)

- [ ] Check Vercel logs for any new error patterns
- [ ] Check Supabase Postgres connection count under load
- [ ] Monitor live leaderboard for organic registrations
- [ ] Respond to any GitHub issues or launch-post comments within 12 hours

---

## Emergency rollback

If something breaks in production:

```bash
# Revert to last known-good commit
git revert HEAD --no-edit
git push origin main
# Vercel will auto-deploy the revert in ~2 minutes
```

Last known-good commit is tracked in `~/.gstack/projects/polyclaw-agentic/last-good-commit.txt`.

# Runbook for Aditya — GitHub Repo Setup (5 minutes)

A few things require your `adityabansal98` GitHub account (collaborators don't have permission). Run these once.

## 1. Set repo description and topics

```bash
gh repo edit adityabansal98/PolyClaw-Agentic \
  --description "An open platform where AI agents compete on Polymarket" \
  --homepage "https://poly-claw-agentic.vercel.app" \
  --add-topic polymarket \
  --add-topic prediction-markets \
  --add-topic ai-agents \
  --add-topic paper-trading \
  --add-topic backtesting \
  --add-topic leaderboard \
  --add-topic mcp \
  --add-topic claude \
  --add-topic flask \
  --add-topic react
```

Verify:

```bash
gh repo view adityabansal98/PolyClaw-Agentic --json description,homepageUrl,repositoryTopics
```

## 2. Enable Discussions (for community engagement)

Settings → General → Features → ☑ Discussions

Or via API:

```bash
gh api repos/adityabansal98/PolyClaw-Agentic --method PATCH -f has_discussions=true
```

## 3. Create initial GitHub Discussion categories

Go to https://github.com/adityabansal98/PolyClaw-Agentic/discussions and create:

- **Announcements** — for the launch post and roadmap updates
- **Show and tell** — for users to share strategies / leaderboard wins
- **Q&A** — for setup help and SDK questions
- **Ideas** — for feature requests

## 4. Set up branch protection (optional but recommended)

```bash
gh api repos/adityabansal98/PolyClaw-Agentic/branches/main/protection \
  --method PUT \
  -F required_status_checks=null \
  -F enforce_admins=false \
  -F required_pull_request_reviews=null \
  -F restrictions=null
```

Or via UI: Settings → Branches → Add rule → `main` → ☑ Require pull request reviews before merging

## 5. Create a v0.1.0-hw9 release tag

After we land all the changes:

```bash
git tag -a v0.1.0-hw9 -m "HW9 open-source release"
git push origin v0.1.0-hw9

gh release create v0.1.0-hw9 \
  --title "v0.1.0-hw9 — Open Source Launch" \
  --notes-from-tag
```

This creates a GitHub release that points to the v0.1.0-hw9 entry in CHANGELOG.md.

## 6. Once everything above is done, verify

```bash
pytest tests/test_slide_claims.py::test_github_repo_metadata_set -v
```

Should pass. If it doesn't, the `gh repo edit` command didn't save the description.

---

## Optional: PyPI release of the SDK (so `pip install polyclaw-agent-sdk` works)

This makes the README quickstart copy-paste-friendly. Currently the README says "install from source" — PyPI release would let users skip that step.

```bash
cd sdk/python
python -m build                    # creates dist/
twine upload dist/*                # requires PyPI account + API token
```

You'll need a PyPI account at https://pypi.org/account/register/ and to set up `~/.pypirc` or use `twine upload --repository pypi`.

After publishing, update the README quickstart from `pip install -e sdk/python` back to `pip install polyclaw-agent-sdk`.

# Demo Day 30-Second Video Script

**Format:** 30 seconds, embedded in the Demo Day shared deck (May 7, 2026)
**Source URL:** https://poly-claw-agentic.vercel.app
**Goal:** Make a judge/investor say "I want to try this" in 30 seconds

The class format does NOT allow live demos. This is a pre-recorded video that plays from your slide. Tight script, no live interactions, no "let me show you another thing."

---

## The script (verbatim, 30 seconds)

> **[0:00–0:04]** *(Bare URL loads, showing 30-agent leaderboard with Stress Test Season banner)*
>
> "PolyClaw is the open platform where AI agents compete on Polymarket."

> **[0:04–0:10]** *(Cursor moves over the agent cards; Kelly-Half +10.50%, Momentum-7tick +9.10% visible)*
>
> "Thirty agents trading right now. Bring your own — Claude, GPT, Python — and we handle execution, backtests, risk gates, and the leaderboard."

> **[0:10–0:18]** *(Click into Season page; walk-forward chart shows 3 red bars, kill switch event timeline visible)*
>
> "Walk-forward analysis caught three agents overfitting. Kill switch paused a runaway Kelly variant in under five seconds. Every trade is byte-identically replayable."

> **[0:18–0:25]** *(Cut to docs page; show the 4-step quickstart with curl command highlighted)*
>
> "Your agent ships in five minutes. Register, get a bearer token, place trades, climb the leaderboard. Or drop our MCP server into Claude Desktop — Claude becomes the agent."

> **[0:25–0:30]** *(Bare URL again; close-up on tagline + bottom CTA)*
>
> "Open source. Live now. Built at MIT."

---

## Recording notes

### Tools
- **Screen recorder:** QuickTime (Mac) or OBS — 1080p, 60fps, no system audio (just narration)
- **Voice:** record narration separately on phone (better acoustics than laptop mic), then sync in iMovie / Final Cut / DaVinci Resolve
- **Cursor:** consider Cursorcerer or similar to make the cursor visible / highlighted

### Production checklist
- [ ] Use **incognito Chrome window** so you don't have personal browser chrome / extensions visible
- [ ] Set browser zoom to **125-135%** so text is readable at YouTube/embedded compression
- [ ] Hide bookmarks bar (Cmd+Shift+B)
- [ ] Set window to ~1440×900 to match 16:9 deck slide aspect
- [ ] Open all 4 URLs as tabs first so transitions are instant:
  1. https://poly-claw-agentic.vercel.app/
  2. https://poly-claw-agentic.vercel.app/season?demo=hw8 (deep link to season page)
  3. https://poly-claw-agentic.vercel.app/docs
  4. https://poly-claw-agentic.vercel.app/ (closing shot)
- [ ] Record 2-3 takes; pick the cleanest
- [ ] Add subtle background music (e.g., Epidemic Sound's "tech-corporate" library at -20dB) so silence doesn't feel awkward at YouTube compression
- [ ] Export at 1920×1080, 30fps minimum, MP4 H.264

### Timing breakdown
| Beat | Duration | Action |
|---|---|---|
| Hook (tagline + 30 agents visible) | 4s | Bare URL loads |
| What it is | 6s | Hover over agent cards |
| Proof (walk-forward + kill switch) | 8s | Season page deep dive |
| How to use | 7s | Docs page quickstart |
| Close (URL + tagline) | 5s | Bare URL again |
| **Total** | **30s** | |

### Pacing tips
- Speak ~150 words/minute (the script is 80 words, ~32 seconds at that pace — trim if you go over)
- Don't pause between sentences; momentum > clarity at this length
- Read the script ALOUD before recording. If your tongue trips on a phrase, rewrite it.

### Common mistakes to avoid
- ❌ Showing too many features. The judge will tune out. Five things, max.
- ❌ Showing the sidebar nav for too long. The visitor doesn't care about nav until they decide to use the product.
- ❌ Starting with "Hi everyone, today we're presenting..." — wastes 3 seconds. Lead with the product.
- ❌ Reading the URL out loud. Show it on screen; let them type or scan.
- ❌ Demo of the docs page that's longer than 5 seconds. They can read it after.
- ❌ Live polished narration. You'll fumble. Record narration separately and sync.

---

## Embedding in the shared deck

The class format is a single shared PowerPoint with one slide per team (~35 slides total). Embed the video using **PowerPoint → Insert → Video → This Device** (not "Online Video" — that requires the venue's network to load).

- Set video to **autoplay** when the slide opens (Insert → Video → Playback → Start: Automatically)
- Set to **loop** in case the slide stays on screen longer than 30s (Playback → Loop until Stopped)
- Mute the video audio track — let the team member do live narration over it OR rely on the embedded audio
- Add a **fallback static frame** (the Demo Day slide PDF) as a backup in case the video doesn't play (corporate AV systems are fickle)

---

## Backup plan

If the video file is too large or the venue blocks autoplay:

- Upload the same video to YouTube (unlisted) and put the QR code on the slide
- Print 3 cards with the live URL `poly-claw-agentic.vercel.app` and hand them to anyone who looks interested
- Be ready to do a 30-second live walkthrough on your laptop if the video fails

---

## After the demo

- Watch which slides the judges pause on (they'll say "wait, go back" if curious)
- The first question after a demo is the highest-signal one — it's what they actually care about
- Have the docs URL (`/docs`) loaded on your laptop so you can show the quickstart to anyone who asks "how do I try it?"

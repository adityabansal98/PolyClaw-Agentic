# PolyClaw Dashboard Frontend

Internal desktop-first dashboard for:

- reviewing new candidate bets before execution
- monitoring open live positions
- routing ideas to paper trading first
- checking service health, logs, and kill-switch state

## Current State

This frontend is intentionally wired to **mock data** for now so the UI can move in parallel with backend work.

What is already included:

- local prototype auth with named users
- Overview, Opportunities, Positions, Paper Trading, and Operations views
- opportunity approval flow with confirmation modal
- paper-first promotion workflow
- note taking and attachment/link UI
- safety states for kill switch and backend health

## Local Run

From the repo root:

```bash
cd frontend
npm install
npm run dev
```

Then open the local Vite URL shown in the terminal.

Prototype login:

- `alex@polyclaw.local`
- password: `demo1234`

You can also create extra prototype users from the login screen.

## Build

```bash
cd frontend
npm run build
```

## Planned Backend Integration

The frontend is designed so the mock layer can later be replaced with backend APIs for:

- auth
- dashboard summaries
- opportunities queue
- opportunity detail, notes, attachments, and approvals
- live and paper positions
- kill switch and service health
- operations logs

See [docs/api-contract.md](./docs/api-contract.md) for the assumed data contract.

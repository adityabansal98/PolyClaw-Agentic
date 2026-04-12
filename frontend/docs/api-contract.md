# Dashboard API Contract Draft

This draft defines the backend shape the frontend is already assuming.

## 1. Authentication

### `POST /api/auth/login`

Request:

```json
{
  "email": "alex@polyclaw.local",
  "password": "demo1234"
}
```

Response:

```json
{
  "user": {
    "id": "user-alex",
    "name": "Alex Chen",
    "email": "alex@polyclaw.local",
    "role": "trader"
  },
  "sessionToken": "..."
}
```

### `POST /api/auth/register`

Request:

```json
{
  "name": "Jordan Smith",
  "email": "jordan@polyclaw.local",
  "password": "secret",
  "role": "trader"
}
```

## 2. Overview

### `GET /api/dashboard/overview`

Response:

```json
{
  "lastRefreshAt": "2026-04-12T16:12:00.000Z",
  "liveSummary": {
    "environment": "live",
    "totalReturnImmediate": 2267.98,
    "openExposure": 16200,
    "availableCapital": 139800,
    "activePositions": 4,
    "pendingApprovals": 5,
    "realizedPnl": 1820,
    "unrealizedPnl": 301.98,
    "dailyPnl": 112.5,
    "liquidationValue": 16501.98
  },
  "paperSummary": {
    "environment": "paper",
    "totalReturnImmediate": 273.11,
    "openExposure": 4700,
    "availableCapital": 95300,
    "activePositions": 2,
    "pendingApprovals": 1,
    "realizedPnl": 240,
    "unrealizedPnl": 92.95,
    "dailyPnl": 19.8,
    "liquidationValue": 4792.95
  },
  "alerts": [
    {
      "id": "alert-opportunity-queue",
      "tone": "neutral",
      "title": "5 new opportunities are waiting for review",
      "description": "1 opportunities remain in paper-first validation."
    }
  ]
}
```

## 3. Opportunities

### `GET /api/opportunities`

Returns the full candidate queue. Each opportunity should include:

```json
{
  "id": "opp-nba-knicks-game1",
  "question": "Will the Knicks win Game 1 vs the 76ers?",
  "category": "NBA",
  "marketType": "Series opener",
  "side": "YES",
  "marketProbability": 0.48,
  "modelProbability": 0.582,
  "edge": 0.102,
  "expectedReturn": 0.091,
  "confidence": 0.917,
  "liquidity": 702000,
  "volume24h": 214000,
  "marketDepth": 130000,
  "spreadBps": 180,
  "urgencyScore": 0.81,
  "signalStrength": 0.88,
  "discoveredAt": "2026-04-12T15:48:00.000Z",
  "lastUpdatedAt": "2026-04-12T16:12:00.000Z",
  "resolutionDate": "2026-04-13T23:30:00.000Z",
  "timeHorizon": "2-8 hours",
  "recommendedStake": 4200,
  "maxStake": 7000,
  "entryPriceMin": 0.47,
  "entryPriceMax": 0.49,
  "slippageLimitBps": 35,
  "currentStage": "new",
  "statusLabel": "Awaiting review",
  "strategySummary": "Fast-moving playoff market with improving model edge after injury and lineup updates.",
  "thesis": "The current market is still pricing the 76ers at pre-news levels...",
  "invalidation": "Edge collapses if the price trades above 0.51...",
  "riskFlags": ["Injury-news sensitivity"],
  "tags": ["strong-edge", "playoff"],
  "relatedExposure": 11800,
  "correlationWarning": "Already long one NBA playoff position...",
  "reviewer": null,
  "reviewedAt": null,
  "priceHistory": [0.43, 0.44, 0.46, 0.47, 0.48],
  "notes": [],
  "attachments": []
}
```

### Opportunity actions

#### `POST /api/opportunities/:id/approve-live`

```json
{
  "stakeOverride": 4200,
  "userId": "user-alex"
}
```

#### `POST /api/opportunities/:id/send-to-paper`

```json
{
  "stakeOverride": 2500,
  "userId": "user-alex"
}
```

#### `POST /api/opportunities/:id/reject`

```json
{
  "userId": "user-alex"
}
```

#### `POST /api/opportunities/:id/promote-to-live`

```json
{
  "stakeOverride": 2500,
  "userId": "user-alex"
}
```

### Notes and attachments

#### `POST /api/opportunities/:id/notes`

```json
{
  "text": "Passing for now because this category is overexposed.",
  "context": "decision",
  "userId": "user-alex"
}
```

#### `POST /api/opportunities/:id/attachments/link`

```json
{
  "title": "Research memo",
  "url": "https://example.com/memo",
  "userId": "user-alex"
}
```

#### `POST /api/opportunities/:id/attachments/file`

`multipart/form-data`

Fields:

- `file`
- `userId`

## 4. Positions

### `GET /api/positions?environment=live`
### `GET /api/positions?environment=paper`

Each position should include:

```json
{
  "id": "pos-live-celtics",
  "opportunityId": "seed-celtics",
  "environment": "live",
  "question": "Will the Celtics beat the Heat on April 14?",
  "category": "NBA",
  "marketType": "Moneyline",
  "side": "YES",
  "shares": 4098.36,
  "stake": 2500,
  "entryPrice": 0.61,
  "currentPrice": 0.646,
  "liquidationValue": 2647.54,
  "unrealizedPnl": 147.54,
  "status": "open",
  "openedAt": "2026-04-11T18:12:00.000Z",
  "updatedAt": "2026-04-12T16:12:00.000Z",
  "modelView": "Still favorable; edge has narrowed but remains positive.",
  "thesisAtEntry": "Early heat fatigue signals and matchup strength favored Boston.",
  "exitGuidance": "Hold unless price exceeds 0.67 before close.",
  "relatedStrategy": "sports-momentum-v2",
  "notes": [],
  "tags": ["nba", "live-book"],
  "priceHistory": [0.6, 0.612, 0.626, 0.638, 0.646]
}
```

### Position actions

#### `POST /api/positions/:id/close`

```json
{
  "userId": "user-alex"
}
```

#### `POST /api/positions/:id/resize`

```json
{
  "direction": "increase",
  "amount": 1000,
  "userId": "user-alex"
}
```

#### `POST /api/positions/:id/mark-review`

```json
{
  "userId": "user-alex"
}
```

#### `POST /api/positions/:id/notes`

```json
{
  "text": "Trim if price breaks 0.67 before close.",
  "context": "decision",
  "userId": "user-alex"
}
```

## 5. Risk and Operations

### `POST /api/risk/pause-category`

```json
{
  "category": "NBA",
  "userId": "user-alex"
}
```

### `POST /api/operations/kill-switch`

```json
{
  "enabled": true,
  "userId": "user-alex"
}
```

### `GET /api/operations/health`

```json
{
  "services": [
    {
      "id": "svc-market-ingestion",
      "name": "Market ingestion",
      "description": "Gamma and market metadata sync",
      "status": "healthy",
      "latencyMs": 182,
      "lastHeartbeatAt": "2026-04-12T16:12:00.000Z",
      "owner": "Data infra",
      "critical": true
    }
  ]
}
```

### `GET /api/operations/logs`

Returns descending recent events:

```json
{
  "logs": [
    {
      "id": "log-1",
      "timestamp": "2026-04-12T16:12:00.000Z",
      "level": "info",
      "source": "strategy-engine",
      "message": "Refreshed 8 candidate opportunities across 5 categories.",
      "user": null,
      "actionRequired": false
    }
  ]
}
```

## 6. Polling Recommendation

Until the backend is ready for push events, the frontend should poll:

- overview and health: every 10-15 seconds
- opportunities queue: every 5-10 seconds
- logs: every 5 seconds
- position detail: refresh when visible, then every 10-15 seconds

WebSockets can be added later for fills, status changes, and urgent alerts.

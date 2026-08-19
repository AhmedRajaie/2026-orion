# RECOVERY.md — restoring this project from backup

## Where the backup actually lives

**GitHub is the backup, not this machine.** Every commit on this machine is
pushed to two branches on `https://github.com/AhmedRajaie/2026-orion`:

- `amrr_waell` — primary
- `amr_wael` — kept in sync as a second copy (historical: pushes to this repo
  started under this name before the branch got renamed locally)

Local git history alone is **not** a backup — if this disk is lost or
corrupted, local commits go with it. What protects you is whatever has
actually been *pushed*. Run `scripts/backup.ps1` regularly (see below) so the
gap between "committed here" and "safe on GitHub" stays small.

**What's *not* covered by this backup:** `.env` (your `GEMINI_API_KEY` /
`FINNHUB_API_KEY`) is deliberately gitignored — it's a secret, not something
to put in a shared GitHub repo. Recovering from backup gets you the code,
data, and trained models, but you'll need to re-create `.env` yourself (see
step 4 below) — it's just two lines, not a real loss.

## How to restore

1. **Clone the repo:**
   ```
   git clone https://github.com/AhmedRajaie/2026-orion.git
   cd 2026-orion
   git checkout amrr_waell
   ```

2. **Install dependencies:**
   ```
   uv sync
   ```

3. **Recreate `.env`** in the repo root (not tracked by git, see above):
   ```
   GEMINI_API_KEY=your-key-here
   FINNHUB_API_KEY=your-key-here
   ```
   The dashboard chat/news features degrade gracefully without this (clear
   in-app error messages, nothing crashes) — add it when you're ready to use
   those features again, it's not blocking for anything else.

4. **Run the dashboard:**
   ```
   uv run uvicorn dashboard.backend.main:app --port 8000
   ```
   Open `http://localhost:8000` (not `127.0.0.1` — the frontend's API calls
   are hardcoded to `http://localhost:8000`, and browsers treat those as
   different origins).

## What to check afterward, to confirm nothing's missing

- [ ] `uv run pytest tests/test_dashboard_backend.py -v` — 32 tests should pass.
- [ ] **Data**: `data/egx/` should have 34 CSVs, `data/egx30.csv` should exist.
- [ ] **Models**: `models/` should have 71 files (34 `lstm_*.pt`, 34 `mlp_*.pt`,
  `lstm_dashboard.pt`, `mlp_dashboard.pt`, `ppo_agent.zip`) — these are now
  tracked in git (they weren't before 2026-08-19; see the "Back up trained
  model checkpoints" commit). Without them, the dashboard still starts, but
  the Model Comparison tab and the "RL Agent (PPO)" strategy silently
  disappear (`main.py` catches `FileNotFoundError` and omits them rather
  than crashing) — so a missing-models problem shows up as missing
  *features*, not an error message. If any are missing after a restore,
  that's the tell.
- [ ] **Asset Management Game specifically**:
  - `dashboard/backend/game_service.py` exists.
  - `GET http://localhost:8000/game/date-bounds` returns a JSON date range
    (confirms the backend endpoints are wired up).
  - Opening the **Asset Game** tab shows the setup screen (starting cash,
    date range, fee toggles) — not a blank tab.
  - `results/reports/game_leaderboard.json` exists and contains your past
    attempts (this file is tracked in git too — a fresh clone should already
    have your history, not start empty).

## Regular backup habit

Run this from the repo root before ending a work session:

```powershell
.\scripts\backup.ps1
```

It stages everything, commits with a timestamp, and pushes to both
`amrr_waell` and `amr_wael` on GitHub. Safe to run even if nothing changed —
it just tells you so and exits. Pass a message if you want one:

```powershell
.\scripts\backup.ps1 -Message "finished the DQN policy comparison"
```

If it fails on the push step, it's almost always a GitHub sign-in prompt
(Git Credential Manager) — complete that and re-run the script.

# Cursor Brief — Save retry window too short to survive a real redeploy/restart

**Requested by:** Mohammed Ismail Pasha, 2026-06-28
**Symptom:** "Network error — could not reach the PVMath server" still appears on Save Project / Proceed to LayoutIQ, despite the earlier hardening fix (`dc6f56e`, "Harden project save against transient network errors").

**File touched:** `frontend/src/lib/api.ts`

---

## Root cause (confirmed in code)

`fetchWithRetry()` (`api.ts:42-51`) retries a failed `fetch()` exactly once, after a fixed 800ms delay:

```js
async function fetchWithRetry(url, init) {
  try {
    return await fetch(url, init);
  } catch (err) {
    await new Promise((r) => setTimeout(r, 800));
    return await fetch(url, init).catch(() => { throw err; });
  }
}
```

800ms is enough to absorb a sub-second network blip, but not enough to survive either of the two situations that actually produce this error in practice:

1. **A real Railway redeploy.** `railway.api.toml` builds with nixpacks and waits on a health check (`healthcheckTimeout = 300`) before cutting traffic over — container build + health check typically takes several seconds to low minutes, not 800ms. Today alone there were 13 commits touching backend files (`api/routers/workflow.py`, `layoutiq/engine.py`, etc.), each implying a fresh deploy cycle if pushed.
2. **A local dev server restart.** If the FastAPI backend runs with `--reload` during active Cursor edits, every saved file restarts the process; any request that lands during that restart window hits a closed port with the same single 800ms retry.

Either way, one retry at a fixed short delay isn't long enough, so the error still surfaces even though the hardening fix is working as designed — it's just sized for the wrong failure window.

## Fix

Replace the single fixed-delay retry with a short bounded retry loop — a few attempts with increasing delay, capped at a total window long enough to ride out a typical redeploy/restart without leaving the user stuck for too long if the server really is down:

```js
async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
  const delaysMs = [800, 2000, 4000, 6000]; // ~13s total before giving up
  let lastErr: unknown;
  for (let attempt = 0; attempt <= delaysMs.length; attempt++) {
    try {
      return await fetch(url, init);
    } catch (err) {
      lastErr = err;
      if (attempt === delaysMs.length) break;
      await new Promise((r) => setTimeout(r, delaysMs[attempt]));
    }
  }
  throw lastErr;
}
```

Optionally surface a "Reconnecting…" state on the Save button while retries are in flight (currently the UI just waits silently until the final failure), so a 13-second retry window doesn't read as a frozen button.

## Out of scope — don't touch unless separately asked

The `geometry_changed` skip-recompute logic in `api/routers/projects.py` (already correct, unrelated to this). `downloadBlob()`'s use of the same `fetchWithRetry` — it inherits the fix automatically since it calls the same function.

## Verify after deploying

1. Push a small backend change, hit Save Project on production within ~5-10 seconds of the push landing, confirm the retry loop now waits it out instead of immediately erroring.
2. If testing against local dev with `--reload`: save a backend file in Cursor, then click Save Project on the app within a couple seconds — confirm it now succeeds instead of erroring.
3. Confirm a genuinely unreachable server (e.g. wrong `VITE_API_URL`, or backend actually down) still surfaces the network-error message after exhausting all retries — should just take ~13s longer to appear than before.

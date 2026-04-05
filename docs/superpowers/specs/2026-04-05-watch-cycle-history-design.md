# Watch Cycle History: Clear & Pagination Improvements

**Date:** 2026-04-05
**Issues:** #36 (clear history button), #22 (bidirectional pagination)
**Status:** Approved

## Problem

The Watch page's Cycle History tab has two usability gaps:

1. **No way to clear accumulated data.** Long-running deployments accumulate cycle history without bound. The only recourse is restarting the process or manipulating the database directly.
2. **No way to navigate back to recent cycles.** Clicking "Load More" replaces the current page with the next one (SWR refetches with a new key). There is no "Previous" or "Back to Latest" control.

## Design

### 1. Backend: `DELETE /api/watch/cycles`

New endpoint on the existing watch router.

- **Method:** `DELETE /cycles`
- **Handler:** Calls `DatabaseService.delete_watch_cycles()` which deletes all rows from the `watch_events` table
- **Response:** `WatchCommandResponse(status="ok", message="Cycle history cleared")`
- **Scope:** Only truncates `watch_events`. Does not touch `watch_commands` or `watch_approvals`.

New database method:

```python
async def delete_watch_cycles(self) -> None:
    conn = await self._get_conn()
    await conn.execute("DELETE FROM watch_events")
    await conn.commit()
```

### 2. Cycle History: Clear History Button

Add a "Clear History" button to `WatchCycleHistory`.

- **Placement:** Header area above the cycle list, right-aligned
- **Style:** `variant="ghost"` `size="sm"`, `Trash2` icon + "Clear History" text
- **Behavior:** Opens an `AlertDialog` confirmation: "This will permanently delete all cycle history. This action cannot be undone."
- **On confirm:** Calls `apiDelete("/api/watch/cycles")`, then calls SWR `mutate` to refresh the cycle list
- **Visibility:** Hidden when cycle list is empty (no cycles to clear)

### 3. Live Stream: Clear Stream Button

Add a "Clear Stream" button to `WatchLiveStream`.

- **Placement:** In the existing header bar, next to the connection badge and event count
- **Style:** `variant="ghost"` `size="sm"`, `Trash2` icon + "Clear Stream" text
- **Behavior:** Calls the existing `clearEvents()` from `useWatchWebSocket`. No confirmation dialog needed since this only clears in-memory state; events remain in the database.
- **Visibility:** Hidden when there are no events

### 4. Accumulating Pagination

Replace the current page-replace behavior with an accumulating pattern.

**Current behavior:** `page` state controls which single page of results is displayed. Changing pages replaces the view entirely.

**New behavior:**
- Maintain an `allCycles` array in component state that accumulates results across pages
- `page` state tracks the next page to fetch
- On mount, fetch page 1 and set `allCycles` to the result
- "Load More" increments `page`, fetches the next page, and **appends** results to `allCycles`
- "Load More" only appears when the last fetched page returned a full 20 results (same as current)
- "Back to Latest" button appears at the top when `page > 1`. Clicking it resets `page` to 1 and replaces `allCycles` with a fresh page 1 fetch
- SWR is used for the initial fetch; subsequent pages use direct `apiGet` calls to avoid SWR key conflicts

## Files Changed

| File | Change |
|------|--------|
| `src/squire/database/service.py` | Add `delete_watch_cycles()` method |
| `src/squire/api/routers/watch.py` | Add `DELETE /cycles` endpoint |
| `web/src/components/watch/watch-cycle-history.tsx` | Clear button with AlertDialog, accumulating pagination with Back to Latest |
| `web/src/components/watch/watch-live-stream.tsx` | Clear Stream button |
| `CHANGELOG.md` | Document changes |

## Not In Scope

- Filtering cycles by status, date range, or event type
- Deleting individual cycles
- Clearing `watch_commands` or `watch_approvals` tables
- New TypeScript types or API client functions (existing `apiGet`/`apiDelete` suffice)

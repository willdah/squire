# Watch Cycle History: Clear & Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clear history buttons and accumulating pagination to the watch cycle history UI.

**Architecture:** New `delete_watch_cycles()` DB method + `DELETE /api/watch/cycles` endpoint for clearing. Frontend gets per-tab clear buttons (with Dialog confirmation for cycle history) and accumulating "Load More" pagination with "Back to Latest" reset.

**Tech Stack:** Python (FastAPI, aiosqlite), React (SWR, shadcn/ui Dialog, lucide-react)

---

### Task 1: Database — `delete_watch_cycles()` method

**Files:**
- Modify: `src/squire/database/service.py:562` (after `get_watch_cycles`)
- Test: `tests/test_database_watch.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_database_watch.py`:

```python
@pytest.mark.asyncio
async def test_delete_watch_cycles(db):
    """delete_watch_cycles removes all watch events."""
    await db.insert_watch_event(cycle=1, type="cycle_start", content="{}")
    await db.insert_watch_event(cycle=1, type="cycle_end", content="{}")
    await db.insert_watch_event(cycle=2, type="cycle_start", content="{}")
    await db.insert_watch_event(cycle=2, type="cycle_end", content="{}")

    await db.delete_watch_cycles()

    events = await db.get_watch_events_since(0)
    assert events == []
    cycles = await db.get_watch_cycles()
    assert cycles == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_database_watch.py::test_delete_watch_cycles -v`
Expected: FAIL with `AttributeError: 'DatabaseService' object has no attribute 'delete_watch_cycles'`

- [ ] **Step 3: Write minimal implementation**

In `src/squire/database/service.py`, add after `get_watch_cycles` (after line 562):

```python
    async def delete_watch_cycles(self) -> None:
        """Delete all watch events (cycle history)."""
        conn = await self._get_conn()
        await conn.execute("DELETE FROM watch_events")
        await conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_database_watch.py::test_delete_watch_cycles -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/squire/database/service.py tests/test_database_watch.py
git commit -m "feat(db): add delete_watch_cycles method

Closes part of #36."
```

---

### Task 2: API — `DELETE /api/watch/cycles` endpoint

**Files:**
- Modify: `src/squire/api/routers/watch.py:113` (after `watch_cycles` endpoint)
- Test: `tests/test_api_watch.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_watch.py`:

```python
@pytest.mark.asyncio
async def test_watch_delete_cycles(db):
    from squire.api.routers.watch import watch_delete_cycles

    await db.insert_watch_event(1, "cycle_start", "{}")
    await db.insert_watch_event(1, "cycle_end", "{}")

    result = await watch_delete_cycles(db=db)
    assert result.status == "ok"
    assert result.message == "Cycle history cleared"

    cycles = await db.get_watch_cycles()
    assert cycles == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_watch.py::test_watch_delete_cycles -v`
Expected: FAIL with `ImportError: cannot import name 'watch_delete_cycles'`

- [ ] **Step 3: Write minimal implementation**

In `src/squire/api/routers/watch.py`, add after the `watch_cycles` endpoint (after line 113):

```python
@router.delete("/cycles", response_model=WatchCommandResponse)
async def watch_delete_cycles(db=Depends(get_db)) -> WatchCommandResponse:
    """Delete all cycle history."""
    await db.delete_watch_cycles()
    return WatchCommandResponse(status="ok", message="Cycle history cleared")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_watch.py::test_watch_delete_cycles -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/squire/api/routers/watch.py tests/test_api_watch.py
git commit -m "feat(api): add DELETE /api/watch/cycles endpoint

Closes #36."
```

---

### Task 3: Frontend — Clear Stream button on Live Stream tab

**Files:**
- Modify: `web/src/components/watch/watch-live-stream.tsx`

- [ ] **Step 1: Add Trash2 import**

In `web/src/components/watch/watch-live-stream.tsx`, update the lucide import (there are currently no lucide imports in this file — add one):

At the top of the file, after the existing imports, add:

```tsx
import { Trash2 } from "lucide-react";
```

- [ ] **Step 2: Add the Clear Stream button**

In the header bar `<div>` that contains the Badge and event count (lines 96–103), add the button after the existing `<div>` with the badge/count, before the closing `</div>` of the flex container:

Replace lines 96–103:

```tsx
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <Badge variant={status === "connected" ? "default" : "secondary"} className="text-xs">
            {status}
          </Badge>
          <span className="text-xs text-muted-foreground">{events.length} events</span>
        </div>
      </div>
```

With:

```tsx
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-2">
          <Badge variant={status === "connected" ? "default" : "secondary"} className="text-xs">
            {status}
          </Badge>
          <span className="text-xs text-muted-foreground">{events.length} events</span>
        </div>
        {events.length > 0 && (
          <Button variant="ghost" size="sm" onClick={clearEvents} className="text-xs text-muted-foreground">
            <Trash2 className="h-3.5 w-3.5 mr-1" />
            Clear Stream
          </Button>
        )}
      </div>
```

- [ ] **Step 3: Add Button import**

Add to imports at the top of the file:

```tsx
import { Button } from "@/components/ui/button";
```

- [ ] **Step 4: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/watch/watch-live-stream.tsx
git commit -m "feat(web): add Clear Stream button to live stream tab

Closes part of #36."
```

---

### Task 4: Frontend — Clear History button with confirmation dialog

**Files:**
- Modify: `web/src/components/watch/watch-cycle-history.tsx`

This task uses the existing `Dialog` component (shadcn v4 / base-ui) for a confirmation prompt before deleting.

- [ ] **Step 1: Add imports**

In `web/src/components/watch/watch-cycle-history.tsx`, add these imports at the top:

```tsx
import { apiDelete } from "@/lib/api";
import { Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
```

Also add `useCallback` to the React import:

```tsx
import { useState, useCallback } from "react";
```

- [ ] **Step 2: Add state and clear handler**

Inside the `WatchCycleHistory` component, after the existing state declarations (lines 57–58), add:

```tsx
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [clearing, setClearing] = useState(false);

  const handleClear = useCallback(async () => {
    setClearing(true);
    try {
      await apiDelete("/api/watch/cycles");
      setConfirmOpen(false);
      mutate();
    } finally {
      setClearing(false);
    }
  }, [mutate]);
```

Note: `mutate` will come from SWR — see Step 3.

- [ ] **Step 3: Destructure `mutate` from useSWR**

Change the existing SWR call from:

```tsx
  const { data: cycles } = useSWR(
```

To:

```tsx
  const { data: cycles, mutate } = useSWR(
```

- [ ] **Step 4: Add header with Clear History button and dialog**

Wrap the existing cycle list `<div>` in a fragment and add a header above it. Replace the return block (starting at the `return` on line 73 through the final `</div>` and closing `)` on line 108) with:

```tsx
  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger
            render={
              <Button variant="ghost" size="sm" className="text-xs text-muted-foreground">
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                Clear History
              </Button>
            }
          />
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Clear cycle history?</DialogTitle>
              <DialogDescription>
                This will permanently delete all cycle history. This action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={handleClear} disabled={clearing}>
                {clearing ? "Clearing..." : "Clear History"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
      <div className="rounded-lg border bg-card divide-y">
        {cycles.map((cycle) => {
          const isExpanded = expanded === cycle.cycle;
          const statusColor = cycle.status === "ok" ? "default" : "destructive";

          return (
            <div key={cycle.cycle}>
              <button
                className="w-full flex items-center gap-3 p-3 text-sm hover:bg-accent/50 transition-colors text-left"
                onClick={() => setExpanded(isExpanded ? null : cycle.cycle)}
              >
                {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                <span className="font-medium">Cycle {cycle.cycle}</span>
                <span className="text-muted-foreground text-xs">
                  {cycle.started_at ? new Date(cycle.started_at).toLocaleTimeString() : "—"}
                </span>
                <span className="text-muted-foreground text-xs">{cycle.tool_count} tools</span>
                <Badge variant={statusColor} className="text-xs">{cycle.status}</Badge>
                {cycle.duration_seconds && (
                  <span className="text-muted-foreground text-xs ml-auto">{cycle.duration_seconds.toFixed(1)}s</span>
                )}
              </button>
              {isExpanded && <CycleDetail cycle={cycle.cycle} />}
            </div>
          );
        })}
      </div>
    </div>
  );
```

Note: the "Load More" button is removed here — it will be replaced with accumulating pagination in Task 5.

- [ ] **Step 5: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/watch/watch-cycle-history.tsx
git commit -m "feat(web): add Clear History button with confirmation dialog

Closes #36."
```

---

### Task 5: Frontend — Accumulating pagination with Back to Latest

**Files:**
- Modify: `web/src/components/watch/watch-cycle-history.tsx`

Replace the single-page SWR pattern with an accumulating approach: SWR for page 1 (with revalidation), direct `apiGet` for subsequent pages appended to local state.

- [ ] **Step 1: Add `apiGet` import if not already present**

Verify `apiGet` is imported. It should already be imported from `@/lib/api`. If not, add it:

```tsx
import { apiGet, apiDelete } from "@/lib/api";
```

Also add `useCallback` to the React import if not already there (it was added in Task 4).

- [ ] **Step 2: Replace state and data-fetching logic**

Replace the existing state declarations and SWR call inside `WatchCycleHistory` (everything from `const [page` through the `useSWR` call) with:

```tsx
  const [expanded, setExpanded] = useState<number | null>(null);
  const [extraCycles, setExtraCycles] = useState<WatchCycle[]>([]);
  const [nextPage, setNextPage] = useState(2);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const PER_PAGE = 20;

  const { data: firstPage, mutate } = useSWR(
    "/api/watch/cycles?page=1",
    () => apiGet<WatchCycle[]>(`/api/watch/cycles?page=1&per_page=${PER_PAGE}`),
  );

  const allCycles = firstPage ? [...firstPage, ...extraCycles] : null;

  const handleLoadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const page = await apiGet<WatchCycle[]>(`/api/watch/cycles?page=${nextPage}&per_page=${PER_PAGE}`);
      setExtraCycles((prev) => [...prev, ...page]);
      setHasMore(page.length >= PER_PAGE);
      setNextPage((p) => p + 1);
    } finally {
      setLoadingMore(false);
    }
  }, [nextPage]);

  const handleBackToLatest = useCallback(() => {
    setExtraCycles([]);
    setNextPage(2);
    setHasMore(true);
    mutate();
  }, [mutate]);

  const handleClear = useCallback(async () => {
    setClearing(true);
    try {
      await apiDelete("/api/watch/cycles");
      setConfirmOpen(false);
      setExtraCycles([]);
      setNextPage(2);
      setHasMore(true);
      mutate();
    } finally {
      setClearing(false);
    }
  }, [mutate]);
```

- [ ] **Step 3: Update the empty/loading guards**

Replace the existing loading and empty state checks to use `allCycles`:

```tsx
  if (!allCycles) {
    return <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">Loading cycles...</div>;
  }

  if (allCycles.length === 0) {
    return <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">No cycles recorded yet.</div>;
  }
```

- [ ] **Step 4: Update the render block**

Replace the return block with the full version including Back to Latest and Load More:

```tsx
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          {nextPage > 2 && (
            <Button variant="ghost" size="sm" onClick={handleBackToLatest} className="text-xs text-muted-foreground">
              Back to Latest
            </Button>
          )}
        </div>
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogTrigger
            render={
              <Button variant="ghost" size="sm" className="text-xs text-muted-foreground">
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                Clear History
              </Button>
            }
          />
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Clear cycle history?</DialogTitle>
              <DialogDescription>
                This will permanently delete all cycle history. This action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={handleClear} disabled={clearing}>
                {clearing ? "Clearing..." : "Clear History"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
      <div className="rounded-lg border bg-card divide-y">
        {allCycles.map((cycle) => {
          const isExpanded = expanded === cycle.cycle;
          const statusColor = cycle.status === "ok" ? "default" : "destructive";

          return (
            <div key={cycle.cycle}>
              <button
                className="w-full flex items-center gap-3 p-3 text-sm hover:bg-accent/50 transition-colors text-left"
                onClick={() => setExpanded(isExpanded ? null : cycle.cycle)}
              >
                {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                <span className="font-medium">Cycle {cycle.cycle}</span>
                <span className="text-muted-foreground text-xs">
                  {cycle.started_at ? new Date(cycle.started_at).toLocaleTimeString() : "—"}
                </span>
                <span className="text-muted-foreground text-xs">{cycle.tool_count} tools</span>
                <Badge variant={statusColor} className="text-xs">{cycle.status}</Badge>
                {cycle.duration_seconds && (
                  <span className="text-muted-foreground text-xs ml-auto">{cycle.duration_seconds.toFixed(1)}s</span>
                )}
              </button>
              {isExpanded && <CycleDetail cycle={cycle.cycle} />}
            </div>
          );
        })}
        {hasMore && (
          <div className="p-3 text-center">
            <Button variant="ghost" size="sm" onClick={handleLoadMore} disabled={loadingMore}>
              {loadingMore ? "Loading..." : "Load more"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
```

- [ ] **Step 5: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/watch/watch-cycle-history.tsx
git commit -m "feat(web): accumulating pagination with Back to Latest

Replaces single-page SWR pattern with accumulating Load More
and a Back to Latest reset button.

Closes #22."
```

---

### Task 6: CHANGELOG and final verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update CHANGELOG**

Add entries under `## [Unreleased]`. In the `### Added` section (create it if it doesn't exist under the existing `### Changed` / `### Fixed`), add:

```markdown
### Added

- **Watch:** "Clear History" button on Cycle History tab with confirmation dialog; calls `DELETE /api/watch/cycles` to truncate cycle data (#36)
- **Watch:** "Clear Stream" button on Live Stream tab to clear in-memory event buffer (#36)
- **Watch:** Accumulating "Load More" pagination on Cycle History — cycles append instead of replacing; "Back to Latest" button resets to page 1 (#22)
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass, including the two new ones (`test_delete_watch_cycles`, `test_watch_delete_cycles`).

- [ ] **Step 3: Run lint and format**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: No lint or format errors.

- [ ] **Step 4: Verify frontend build**

Run: `cd web && npx next build`
Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for watch cycle history improvements"
```

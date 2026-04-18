"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * Sync a piece of page state with a single URL search param.
 *
 * Reading the value happens synchronously from `useSearchParams()`, so the
 * current URL is the source of truth. Writing uses `router.replace()` to avoid
 * polluting history with every tab/filter click. When `next` equals
 * `defaultValue`, the key is removed from the URL so bare paths stay clean.
 *
 * Pattern mirrors the existing `useWorkbenchQuery` hook in
 * `web/src/components/watch/investigation-workbench.tsx`.
 */
export function useUrlState<T extends string>(
  key: string,
  defaultValue: T,
): [T, (next: T) => void] {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const raw = searchParams.get(key);
  const value = (raw ?? defaultValue) as T;

  const setValue = useCallback(
    (next: T) => {
      const params = new URLSearchParams(currentSearchString(searchParams));
      if (!next || next === defaultValue) {
        params.delete(key);
      } else {
        params.set(key, next);
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname);
    },
    [searchParams, router, pathname, key, defaultValue],
  );

  return [value, setValue];
}

/**
 * Variant for `Set<string>` state (e.g. expanded row ids), serialized as a
 * comma-separated URL param. Empty sets clear the param.
 */
export function useUrlStateSet(key: string): [Set<string>, (next: Set<string>) => void] {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const raw = searchParams.get(key);
  const value = raw ? new Set(raw.split(",").filter(Boolean)) : new Set<string>();

  const setValue = useCallback(
    (next: Set<string>) => {
      const params = new URLSearchParams(currentSearchString(searchParams));
      if (next.size === 0) {
        params.delete(key);
      } else {
        params.set(key, Array.from(next).join(","));
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname);
    },
    [searchParams, router, pathname, key],
  );

  return [value, setValue];
}

/**
 * Variant for numeric state, serialized with a default so URLs stay clean.
 */
export function useUrlStateNumber(
  key: string,
  defaultValue: number,
): [number, (next: number) => void] {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const raw = searchParams.get(key);
  const parsed = raw === null ? NaN : Number(raw);
  const value = Number.isFinite(parsed) ? parsed : defaultValue;

  const setValue = useCallback(
    (next: number) => {
      const params = new URLSearchParams(currentSearchString(searchParams));
      if (next === defaultValue) {
        params.delete(key);
      } else {
        params.set(key, String(next));
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname);
    },
    [searchParams, router, pathname, key, defaultValue],
  );

  return [value, setValue];
}

/**
 * Return the live URL search string when possible. `useSearchParams()` reflects
 * the snapshot at render time — if two setters from different `useUrlState`
 * hooks fire in the same event handler, the second one would otherwise race
 * against the first's `router.replace()` and clobber it. Next.js's
 * `router.replace()` updates `window.location` synchronously via
 * `history.replaceState()`, so reading from the window lets sequential writes
 * compose.
 */
function currentSearchString(searchParams: ReturnType<typeof useSearchParams>): string {
  if (typeof window !== "undefined") {
    return window.location.search.replace(/^\?/, "");
  }
  return searchParams.toString();
}

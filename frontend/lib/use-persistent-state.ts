"use client";

import { useCallback, useSyncExternalStore, type Dispatch, type SetStateAction } from "react";

export function usePersistentString<T extends string>(key: string, fallback: T): readonly [T, Dispatch<SetStateAction<T>>] {
  const eventName = `finsight:persistent:${key}`;
  const subscribe = useCallback((notify: () => void) => {
    function onStorage(event: StorageEvent) { if (event.key === key) notify(); }
    window.addEventListener("storage", onStorage);
    window.addEventListener(eventName, notify);
    return () => { window.removeEventListener("storage", onStorage); window.removeEventListener(eventName, notify); };
  }, [eventName, key]);
  const getSnapshot = useCallback(() => (window.localStorage.getItem(key) ?? fallback) as T, [fallback, key]);
  const getServerSnapshot = useCallback(() => fallback, [fallback]);
  const value = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const setValue: Dispatch<SetStateAction<T>> = useCallback((next) => {
    const current = (window.localStorage.getItem(key) ?? fallback) as T;
    const resolved = typeof next === "function" ? next(current) : next;
    window.localStorage.setItem(key, resolved);
    window.dispatchEvent(new Event(eventName));
  }, [eventName, fallback, key]);
  return [value, setValue] as const;
}

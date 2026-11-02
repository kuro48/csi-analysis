"use client";

import { useSyncExternalStore } from "react";

let token = "";
const listeners = new Set<() => void>();
export function setOperatorToken(value: string) {
  token = value.trim();
  listeners.forEach((listener) => listener());
}
export function useOperatorToken() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    () => token,
    () => "",
  );
}
export function operatorFetch(url: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (token && !headers.has("Authorization"))
    headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...init, headers });
}

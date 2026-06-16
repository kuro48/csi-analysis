export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const POLL_INTERVAL_MS = 2000;
export const POLL_TIMEOUT_MS = 20 * 60 * 1000;

export const TERMINAL_STATUSES = ["completed", "error"] as const;

export const BREATHING_BAND_HZ: [number, number] = [0.1, 0.5];

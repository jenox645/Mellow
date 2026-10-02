// Shared React hooks.
'use strict';

// sessionStorage: survives switching pages and reloading, not a restart
export function readSession(key, fallback) {
  try {
    const v = sessionStorage.getItem(key);
    return v === null || v === '' ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}

export function hasSession(key) {
  try { return sessionStorage.getItem(key) !== null; } catch { return false; }
}

// useState that is kept in sessionStorage under `key` (JSON)
export function useSessionState(key, initial) {
  const [value, setValue] = React.useState(() => readSession(key, initial));
  React.useEffect(() => {
    try { sessionStorage.setItem(key, JSON.stringify(value)); } catch {}
  }, [key, value]);
  return [value, setValue];
}

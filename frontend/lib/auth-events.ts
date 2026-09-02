export type AuthEventType = "login" | "logout" | "session";

export const AUTH_EVENT_KEY = "finsight_auth_event";
const CHANNEL_NAME = "finsight_auth";

interface AuthEvent {
  type: AuthEventType;
  at: number;
}

function parseEvent(value: unknown): AuthEvent | null {
  if (typeof value !== "string") return null;
  try {
    const parsed = JSON.parse(value) as Partial<AuthEvent>;
    if (
      (parsed.type === "login" || parsed.type === "logout" || parsed.type === "session") &&
      typeof parsed.at === "number"
    ) {
      return parsed as AuthEvent;
    }
  } catch {
    // Ignore malformed events from old clients or manual storage edits.
  }
  return null;
}

export function publishAuthEvent(type: AuthEventType): void {
  if (typeof window === "undefined") return;
  const event: AuthEvent = { type, at: Date.now() };
  if ("BroadcastChannel" in window) {
    const channel = new BroadcastChannel(CHANNEL_NAME);
    channel.postMessage(event);
    channel.close();
  }
  localStorage.setItem(AUTH_EVENT_KEY, JSON.stringify(event));
}

export function subscribeToAuthEvents(listener: (type: AuthEventType) => void): () => void {
  if (typeof window === "undefined") return () => undefined;

  const onStorage = (event: StorageEvent) => {
    if (event.key !== AUTH_EVENT_KEY) return;
    const parsed = parseEvent(event.newValue);
    if (parsed) listener(parsed.type);
  };
  window.addEventListener("storage", onStorage);

  const channel = "BroadcastChannel" in window ? new BroadcastChannel(CHANNEL_NAME) : null;
  if (channel) {
    channel.onmessage = (event: MessageEvent<unknown>) => {
      const value = event.data as Partial<AuthEvent> | null;
      if (
        value &&
        (value.type === "login" || value.type === "logout" || value.type === "session")
      ) {
        listener(value.type);
      }
    };
  }

  return () => {
    window.removeEventListener("storage", onStorage);
    channel?.close();
  };
}

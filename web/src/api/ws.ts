import type { WSMessage } from '../types';

type Listener = (msg: WSMessage) => void;

const wsURL =
  (import.meta.env.VITE_WS_URL as string | undefined) || 'ws://localhost:8000/ws';

/**
 * Resilient WebSocket client for the controller `/ws` endpoint.
 * - Auto-reconnect with capped exponential backoff.
 * - Pub/sub: subscribers receive parsed `WSMessage` objects.
 * - Tolerates non-JSON heartbeats (`ping`/`pong`).
 */
export class CorridorWS {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<(s: WSStatus) => void>();
  private retry = 0;
  private timer: number | null = null;
  private closed = false;
  private status: WSStatus = 'idle';

  constructor(public readonly url: string = wsURL) {}

  connect(): void {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;
    this.closed = false;
    this.setStatus('connecting');
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url);
    } catch (err) {
      this.scheduleReconnect();
      return;
    }
    this.ws = socket;
    socket.onopen = () => {
      this.retry = 0;
      this.setStatus('open');
    };
    socket.onmessage = (ev) => {
      const data = typeof ev.data === 'string' ? ev.data : '';
      if (!data || data === 'ping' || data === 'pong') return;
      try {
        const parsed = JSON.parse(data) as WSMessage;
        if (!parsed || typeof parsed !== 'object' || !('topic' in parsed)) return;
        for (const l of this.listeners) l(parsed);
      } catch {
        // Ignore malformed messages instead of crashing the UI.
      }
    };
    socket.onerror = () => {
      this.setStatus('error');
    };
    socket.onclose = () => {
      this.setStatus('closed');
      if (!this.closed) this.scheduleReconnect();
    };
  }

  send(msg: unknown): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
      return true;
    }
    return false;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onStatus(listener: (s: WSStatus) => void): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  close(): void {
    this.closed = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  private setStatus(s: WSStatus) {
    this.status = s;
    for (const l of this.statusListeners) l(s);
  }

  private scheduleReconnect() {
    if (this.closed) return;
    const delay = Math.min(1000 * 2 ** this.retry, 15000);
    this.retry += 1;
    this.timer = window.setTimeout(() => this.connect(), delay);
  }
}

export type WSStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

let singleton: CorridorWS | null = null;

export function getWS(): CorridorWS {
  if (!singleton) {
    singleton = new CorridorWS();
  }
  return singleton;
}

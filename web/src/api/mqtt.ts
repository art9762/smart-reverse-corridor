import mqtt, { MqttClient, IClientOptions } from 'mqtt';
import type { WSMessage, WorldSnapshot } from '../types';
import { useDashboard } from '../store';

const url = import.meta.env.VITE_MQTT_WS_URL as string | undefined;

const CONNECT_TIMEOUT_MS = 4000;

/**
 * Optional direct subscription to the mosquitto WebSocket broker.
 * Not required for the dashboard to function — the controller relays
 * everything over `/ws`. Use this when you want raw MQTT firehose
 * on the same machine as the broker (e.g. demo over LAN).
 *
 * Subscribes to:
 *   - corridor/state, corridor/metrics/tick, corridor/alerts, corridor/cam/#
 *     (forwarded to the supplied `onMessage` callback)
 *   - corridor/sim/world — pushed straight into the dashboard store via
 *     `ingestWorld`. The controller does not republish this topic over /ws,
 *     so the dashboard relies on the direct mosquitto WS feed for the live
 *     world snapshot.
 *
 * If the broker is unreachable (no VITE_MQTT_WS_URL or connect timeout)
 * we log a warning and return null without throwing — the rest of the
 * dashboard keeps working off the controller WS relay.
 */
export function connectMqtt(
  onMessage: (msg: WSMessage) => void,
  onStatus?: (state: 'connecting' | 'connected' | 'reconnecting' | 'closed') => void,
  options: IClientOptions = {},
): MqttClient | null {
  if (!url) return null;
  onStatus?.('connecting');

  let client: MqttClient;
  try {
    client = mqtt.connect(url, {
      reconnectPeriod: 3000,
      connectTimeout: CONNECT_TIMEOUT_MS,
      keepalive: 30,
      clean: true,
      ...options,
    });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[mqtt] failed to start client, live world stream disabled:', err);
    onStatus?.('closed');
    return null;
  }

  const TOPICS = [
    'corridor/state',
    'corridor/metrics/tick',
    'corridor/alerts',
    'corridor/cam/#',
    'corridor/sim/world',
  ];

  // If we never connect within the timeout, warn once and let mqtt
  // continue trying in the background (no throw).
  let connected = false;
  const timer = setTimeout(() => {
    if (!connected) {
      // eslint-disable-next-line no-console
      console.warn(
        `[mqtt] not connected to ${url} within ${CONNECT_TIMEOUT_MS}ms; live world stream may be unavailable`,
      );
    }
  }, CONNECT_TIMEOUT_MS);

  client.on('connect', () => {
    connected = true;
    clearTimeout(timer);
    onStatus?.('connected');
    client.subscribe(TOPICS, { qos: 1 }, (err) => {
      if (err) {
        // eslint-disable-next-line no-console
        console.warn('[mqtt] subscribe error:', err);
      }
    });
  });
  client.on('reconnect', () => onStatus?.('reconnecting'));
  client.on('close', () => {
    clearTimeout(timer);
    onStatus?.('closed');
  });
  client.on('error', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[mqtt] error:', err?.message ?? err);
  });
  client.on('message', (topic, payload) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(payload.toString());
    } catch {
      // Ignore malformed retained messages.
      return;
    }
    if (topic === 'corridor/sim/world') {
      // Push directly into the store — keep only the latest frame.
      try {
        useDashboard.getState().ingestWorld(parsed as WorldSnapshot);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[mqtt] ingestWorld failed:', err);
      }
      return;
    }
    try {
      onMessage({ topic, payload: parsed } as WSMessage);
    } catch {
      // Defensive: never let a single bad payload kill the subscription.
    }
  });

  return client;
}

export const mqttWsUrl = url ?? null;

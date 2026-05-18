import mqtt, { MqttClient, IClientOptions } from 'mqtt';
import type { WSMessage } from '../types';

const url = import.meta.env.VITE_MQTT_WS_URL as string | undefined;

/**
 * Optional direct subscription to the mosquitto WebSocket broker.
 * Not required for the dashboard to function — the controller relays
 * everything over `/ws`. Use this when you want raw MQTT firehose
 * on the same machine as the broker (e.g. demo over LAN).
 */
export function connectMqtt(
  onMessage: (msg: WSMessage) => void,
  onStatus?: (state: 'connecting' | 'connected' | 'reconnecting' | 'closed') => void,
  options: IClientOptions = {},
): MqttClient | null {
  if (!url) return null;
  onStatus?.('connecting');
  const client = mqtt.connect(url, {
    reconnectPeriod: 3000,
    keepalive: 30,
    clean: true,
    ...options,
  });

  const TOPICS = ['corridor/state', 'corridor/metrics/tick', 'corridor/alerts', 'corridor/cam/#'];

  client.on('connect', () => {
    onStatus?.('connected');
    client.subscribe(TOPICS, { qos: 1 });
  });
  client.on('reconnect', () => onStatus?.('reconnecting'));
  client.on('close', () => onStatus?.('closed'));
  client.on('message', (topic, payload) => {
    try {
      const parsed = JSON.parse(payload.toString());
      onMessage({ topic, payload: parsed } as WSMessage);
    } catch {
      // Ignore malformed retained messages.
    }
  });

  return client;
}

export const mqttWsUrl = url ?? null;

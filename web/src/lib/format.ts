/** Time/number formatting helpers used throughout the dashboard. */

export const formatSeconds = (s: number): string => {
  if (!Number.isFinite(s) || s < 0) return '0s';
  const sec = Math.round(s);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const r = sec % 60;
  return `${m}m ${r.toString().padStart(2, '0')}s`;
};

export const formatClock = (epochSeconds: number): string => {
  if (!epochSeconds) return '—';
  const d = new Date(epochSeconds * 1000);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString([], { hour12: false });
};

export const formatNumber = (n: number, opts: Intl.NumberFormatOptions = {}): string =>
  new Intl.NumberFormat('en-US', { maximumFractionDigits: 1, ...opts }).format(n);

export const formatPercent = (n: number): string =>
  `${Math.round(Math.max(0, Math.min(1, n)) * 100)}%`;

export const formatHz = (n: number): string => `${formatNumber(n, { maximumFractionDigits: 1 })} Hz`;

export const clamp = (v: number, lo: number, hi: number): number =>
  Math.max(lo, Math.min(hi, v));

export const phaseLabel = (p: string): string =>
  p
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c: string) => c.toUpperCase());

export const nowSeconds = (): number => Date.now() / 1000;

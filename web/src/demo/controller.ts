/**
 * DemoController — TypeScript port of the Python corridor controller FSM.
 *
 * Runs the phase finite-state machine in the browser. The orchestrator drives
 * it once per game-loop frame by calling `tick(nowS)`.
 *
 * Phase sequence (mirrors services/controller/app/fsm.py):
 *
 *   RED_BOTH → GREEN_A → YELLOW_A → ALL_RED_AFTER_A →
 *              GREEN_B → YELLOW_B → ALL_RED_AFTER_B → (back to RED_BOTH)
 *
 * Scheduler mirrors services/controller/app/scheduler.py:
 *   T_green = clamp(base + a*queue + b*wait_other − c*other_empty, min, max)
 *
 * In 'baseline' mode a fixed midpoint green duration is used.
 */

import type { Phase } from '../types';

// ── Timings ────────────────────────────────────────────────────────────────

export interface ControllerTimings {
  greenMinS: number;
  greenMaxS: number;
  baseGreenS: number;
  yellowS: number;
  allRedGuardS: number;
  clearTimeoutS: number;
  /** Priority weight: queue length */
  prioWQueue: number;
  /** Priority weight: wait time of other side */
  prioWWait: number;
  /** Priority weight: other side is empty bonus (subtractive) */
  prioWOtherEmpty: number;
  /** Priority weight: truck presence multiplier */
  prioWTruck: number;
}

export const DEFAULT_TIMINGS: ControllerTimings = {
  greenMinS: 15,
  greenMaxS: 90,
  baseGreenS: 30,
  yellowS: 3,
  allRedGuardS: 5,
  clearTimeoutS: 60,
  prioWQueue: 2.0,
  prioWWait: 0.5,
  prioWOtherEmpty: 5.0,
  prioWTruck: 0,
};

// ── Phase FSM ──────────────────────────────────────────────────────────────

type FSMState =
  | 'INIT'
  | 'RED_BOTH'
  | 'GREEN_A'
  | 'YELLOW_A'
  | 'ALL_RED_AFTER_A'
  | 'GREEN_B'
  | 'YELLOW_B'
  | 'ALL_RED_AFTER_B'
  | 'EMERGENCY_STOP';

function fsmToPhase(state: FSMState): Phase {
  switch (state) {
    case 'GREEN_A':        return 'GREEN_A';
    case 'YELLOW_A':       return 'YELLOW_A';
    case 'GREEN_B':        return 'GREEN_B';
    case 'YELLOW_B':       return 'YELLOW_B';
    case 'ALL_RED_AFTER_A':
    case 'ALL_RED_AFTER_B':
    case 'RED_BOTH':       return 'RED_BOTH';
    case 'EMERGENCY_STOP': return 'ALL_RED';
    default:               return 'RED_BOTH';
  }
}

// ── DemoController ─────────────────────────────────────────────────────────

export class DemoController {
  private timings: ControllerTimings;
  private mode: 'baseline' | 'adaptive' = 'adaptive';

  // FSM state
  private fsmState: FSMState = 'INIT';
  private phaseStartedAt = 0;        // real seconds (Date.now()/1000)
  private phaseDeadline = 0;         // real seconds when current phase expires
  private lastYellowEndedAt: number | null = null;
  private lastGreenSide: 'A' | 'B' | null = null;
  private lastWaitStartedA = 0;      // when A-side started waiting
  private lastWaitStartedB = 0;

  // Inputs fed by orchestrator each frame
  private queueA = 0;
  private queueB = 0;
  private insideA = 0;
  private insideB = 0;

  // Stuck-zone clear tracking
  private zoneClearStartedAt: number | null = null;
  private _emergencyActive = false;

  // Planned end time (for CorridorState)
  private phasePlannedEndAt = 0;

  constructor(timings: Partial<ControllerTimings> = {}) {
    this.timings = { ...DEFAULT_TIMINGS, ...timings };
  }

  // ── Public API ────────────────────────────────────────────────────────────

  setMode(mode: 'baseline' | 'adaptive'): void {
    this.mode = mode;
  }

  setWeights(weights: Partial<Pick<ControllerTimings,
    'prioWQueue' | 'prioWWait' | 'prioWOtherEmpty' | 'prioWTruck'
  >>): void {
    Object.assign(this.timings, weights);
  }

  /** Feed current queue and inside counts before calling tick(). */
  feedCounts(queueA: number, queueB: number, insideA: number, insideB: number): void {
    this.queueA = queueA;
    this.queueB = queueB;
    this.insideA = insideA;
    this.insideB = insideB;
  }

  get phase(): Phase {
    return fsmToPhase(this.fsmState);
  }

  get phaseStartAt(): number {
    return this.phaseStartedAt;
  }

  get phaseEndAt(): number {
    return this.phasePlannedEndAt;
  }

  isEmergency(): boolean {
    return this._emergencyActive;
  }

  /** Boot the controller. Must be called once before tick(). */
  boot(nowS: number): void {
    this.fsmState = 'RED_BOTH';
    this.phaseStartedAt = nowS;
    this.phasePlannedEndAt = nowS + this.timings.allRedGuardS;
    this.phaseDeadline = nowS + this.timings.allRedGuardS;
    this.lastWaitStartedA = nowS;
    this.lastWaitStartedB = nowS;
  }

  /** Advance the FSM. Called every frame by the orchestrator. */
  tick(nowS: number): Phase {
    if (this.fsmState === 'INIT') return this.phase;
    if (nowS < this.phaseDeadline) return this.phase;

    this._advance(nowS);
    return this.phase;
  }

  /** Operator: force a specific phase (used by UI overrides). */
  forcePhase(phase: Phase, nowS: number): void {
    switch (phase) {
      case 'GREEN_A':
        this._transition('GREEN_A', nowS, this._computeGreen('A', nowS));
        this.lastGreenSide = 'A';
        break;
      case 'GREEN_B':
        this._transition('GREEN_B', nowS, this._computeGreen('B', nowS));
        this.lastGreenSide = 'B';
        break;
      case 'RED_BOTH':
      case 'ALL_RED':
        this._toRedBoth(nowS, 1.0);
        break;
    }
  }

  /** Operator: emergency stop. */
  emergencyStop(nowS: number): void {
    this._emergencyActive = true;
    this.fsmState = 'EMERGENCY_STOP';
    this.phaseStartedAt = nowS;
    this.phasePlannedEndAt = Infinity;
    this.phaseDeadline = Infinity;
  }

  /** Operator: resume from emergency. */
  resume(nowS: number): void {
    if (!this._emergencyActive) return;
    this._emergencyActive = false;
    this._toRedBoth(nowS, 1.0);
  }

  /** Reset all state. */
  reset(nowS: number): void {
    this.fsmState = 'INIT';
    this._emergencyActive = false;
    this.queueA = 0;
    this.queueB = 0;
    this.insideA = 0;
    this.insideB = 0;
    this.lastGreenSide = null;
    this.lastYellowEndedAt = null;
    this.zoneClearStartedAt = null;
    this.boot(nowS);
  }

  // ── FSM advance ───────────────────────────────────────────────────────────

  private _advance(nowS: number): void {
    const s = this.fsmState;

    if (s === 'EMERGENCY_STOP') return;

    if (s === 'RED_BOTH') {
      this._tryGoGreen(nowS);
      return;
    }
    if (s === 'GREEN_A' || s === 'GREEN_B') {
      // Transition to YELLOW
      this._toYellow(nowS);
      return;
    }
    if (s === 'YELLOW_A') {
      this._transition('ALL_RED_AFTER_A', nowS, this.timings.allRedGuardS);
      this.lastYellowEndedAt = nowS;
      this.zoneClearStartedAt = nowS;
      return;
    }
    if (s === 'YELLOW_B') {
      this._transition('ALL_RED_AFTER_B', nowS, this.timings.allRedGuardS);
      this.lastYellowEndedAt = nowS;
      this.zoneClearStartedAt = nowS;
      return;
    }
    if (s === 'ALL_RED_AFTER_A') {
      if (this._tryGoGreenSide('B', nowS)) {
        this.zoneClearStartedAt = null;
      } else {
        this._checkClearTimeout(nowS);
        this.phaseDeadline = nowS + 0.5;
      }
      return;
    }
    if (s === 'ALL_RED_AFTER_B') {
      if (this._tryGoGreenSide('A', nowS)) {
        this.zoneClearStartedAt = null;
      } else {
        this._checkClearTimeout(nowS);
        this.phaseDeadline = nowS + 0.5;
      }
      return;
    }
  }

  private _tryGoGreen(nowS: number): boolean {
    // Pick side with more demand; alternate on tie
    const side = this._pickNextSide();
    return this._tryGoGreenSide(side, nowS);
  }

  private _tryGoGreenSide(side: 'A' | 'B', nowS: number): boolean {
    if (!this._canGoGreen(nowS)) {
      this.phaseDeadline = nowS + 0.5;
      return false;
    }
    const duration = this._computeGreen(side, nowS);
    const state: FSMState = side === 'A' ? 'GREEN_A' : 'GREEN_B';
    this._transition(state, nowS, duration);
    this.lastGreenSide = side;
    if (side === 'A') {
      this.lastWaitStartedA = nowS;
    } else {
      this.lastWaitStartedB = nowS;
    }
    return true;
  }

  private _toYellow(nowS: number): void {
    const next: FSMState = this.fsmState === 'GREEN_A' ? 'YELLOW_A' : 'YELLOW_B';
    this._transition(next, nowS, this.timings.yellowS);
  }

  private _toRedBoth(nowS: number, duration = 1.0): void {
    this._transition('RED_BOTH', nowS, duration);
  }

  private _transition(state: FSMState, nowS: number, duration: number): void {
    this.fsmState = state;
    this.phaseStartedAt = nowS;
    this.phasePlannedEndAt = nowS + duration;
    this.phaseDeadline = nowS + duration;
  }

  // ── Guards & helpers ──────────────────────────────────────────────────────

  private _canGoGreen(nowS: number): boolean {
    // Zone must be empty
    if (this.insideA > 0 || this.insideB > 0) return false;
    // ALL_RED guard must have elapsed since last yellow
    if (this.lastYellowEndedAt !== null) {
      if (nowS - this.lastYellowEndedAt < this.timings.allRedGuardS) return false;
    }
    return true;
  }

  private _pickNextSide(): 'A' | 'B' {
    if (this.queueA > this.queueB) return 'A';
    if (this.queueB > this.queueA) return 'B';
    // Tie — alternate
    return this.lastGreenSide === 'A' ? 'B' : 'A';
  }

  private _computeGreen(side: 'A' | 'B', nowS: number): number {
    const { greenMinS, greenMaxS, baseGreenS } = this.timings;
    if (this.mode === 'baseline') {
      return clamp((greenMinS + greenMaxS) / 2, greenMinS, greenMaxS);
    }
    // Adaptive
    const queue = side === 'A' ? this.queueA : this.queueB;
    const waitOther = side === 'A'
      ? nowS - this.lastWaitStartedB
      : nowS - this.lastWaitStartedA;
    const otherInsideEmpty = side === 'A'
      ? this.insideB === 0 && this.queueB === 0
      : this.insideA === 0 && this.queueA === 0;

    const raw =
      baseGreenS
      + this.timings.prioWQueue * Math.max(0, queue)
      + this.timings.prioWWait  * Math.max(0, waitOther)
      - this.timings.prioWOtherEmpty * (otherInsideEmpty ? 1 : 0);

    return clamp(raw, greenMinS, greenMaxS);
  }

  private _checkClearTimeout(nowS: number): void {
    if (
      this.zoneClearStartedAt !== null &&
      (this.insideA > 0 || this.insideB > 0) &&
      nowS - this.zoneClearStartedAt >= this.timings.clearTimeoutS
    ) {
      // Zone didn't clear — raise emergency (handled by orchestrator)
      this.emergencyStop(nowS);
    }
  }
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

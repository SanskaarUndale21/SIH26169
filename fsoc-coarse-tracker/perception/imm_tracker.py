"""Interacting Multiple Model (IMM) estimator (Section 7.2).

Design note (documented per Section 16 instruction #9, since this is a
detail not fully pinned down by the spec): all three models share a common
5-dim state [x, y, vx, vy, omega] so mixing/combination across models is a
plain linear-algebra operation on equal-size state vectors, rather than the
heavier variable-dimension IMM formulation. The CT model is the standard
"nearly-constant-turn" linearized model (Bar-Shalom), built each step from
the previous mixed omega estimate; CV and random-walk models freeze omega
and differ only in process noise on velocity. This is a documented, common
simplification -- it keeps the implementation tractable while still giving
each of the three canonical motion behaviours (straight-line, turning,
erratic) its own dedicated filter.

Process noise magnitudes (process_noise_cv/ct/rw) and measurement noise are
config-exposed rather than hardcoded, since the "right" values are scenario
dependent and not specified by the problem statement; defaults were chosen
by hand-tuning against the simulator's own motion models to hit the <=10px
tracking-error target on clean scenarios, then left loose enough to still
track (with degraded but bounded error) under the noisier disturbance
conditions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

STATE_DIM = 5  # x, y, vx, vy, omega
MEAS_DIM = 2


@dataclass
class KalmanModel:
    name: str
    x: np.ndarray  # (5,) state
    P: np.ndarray  # (5,5) covariance
    Q_scale: float  # process noise scale (velocity)
    is_ct: bool = False

    def transition(self, dt: float) -> np.ndarray:
        if self.is_ct:
            return _ct_transition_matrix(self.x[4], dt)
        F = np.eye(STATE_DIM)
        F[0, 2] = dt
        F[1, 3] = dt
        return F

    def process_noise(self, dt: float) -> np.ndarray:
        Q = np.eye(STATE_DIM) * 1e-6
        q = self.Q_scale
        # simple discretized white-noise-acceleration model on vx, vy
        Q[0, 0] = Q[1, 1] = q * dt ** 3 / 3
        Q[2, 2] = Q[3, 3] = q * dt
        Q[0, 2] = Q[2, 0] = Q[1, 3] = Q[3, 1] = q * dt ** 2 / 2
        if self.is_ct:
            Q[4, 4] = 5e-3  # allow omega to keep adapting after its finite-difference seed
        return Q

    def predict(self, dt: float):
        F = self.transition(dt)
        Qm = self.process_noise(dt)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Qm

    def update(self, z: Optional[np.ndarray], R: np.ndarray) -> float:
        """Returns the measurement likelihood (for mode-prob update); if
        z is None (missed detection), skips the correction and returns a
        neutral likelihood so mode probabilities don't get penalized for
        a frame with no measurement at all."""
        H = np.zeros((MEAS_DIM, STATE_DIM))
        H[0, 0] = H[1, 1] = 1.0
        if z is None:
            return 1.0
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(STATE_DIM) - K @ H) @ self.P
        det_s = max(np.linalg.det(S), 1e-9)
        likelihood = math.exp(-0.5 * float(y.T @ np.linalg.inv(S) @ y)) / math.sqrt((2 * math.pi) ** MEAS_DIM * det_s)
        return max(likelihood, 1e-12)


def _ct_transition_matrix(omega: float, dt: float) -> np.ndarray:
    F = np.eye(STATE_DIM)
    if abs(omega) < 1e-4:
        F[0, 2] = dt
        F[1, 3] = dt
        return F
    w = omega
    sw, cw = math.sin(w * dt), math.cos(w * dt)
    F[0, 2] = sw / w
    F[0, 3] = -(1 - cw) / w
    F[1, 2] = (1 - cw) / w
    F[1, 3] = sw / w
    F[2, 2] = cw
    F[2, 3] = -sw
    F[3, 2] = sw
    F[3, 3] = cw
    return F


@dataclass
class IMMConfig:
    q_cv: float = 4.0
    q_ct: float = 4.0
    q_rw: float = 50.0
    measurement_noise: float = 4.0

    @classmethod
    def from_config(cls, cfg: dict) -> "IMMConfig":
        t = cfg.get("tracker", {})
        return cls(
            q_cv=t.get("process_noise_cv", 4.0),
            q_ct=t.get("process_noise_ct", 4.0),
            q_rw=t.get("process_noise_rw", 50.0),
            measurement_noise=t.get("measurement_noise", 4.0),
        )


class IMMTracker:
    MODEL_NAMES = ("cv", "ct", "rw")

    def __init__(self, cfg: IMMConfig, init_pos: Tuple[float, float],
                 init_vel: Tuple[float, float] = (0.0, 0.0)):
        """init_vel: optional finite-difference velocity estimate from the
        two most recent raw detections (see pipeline.py). Starting the
        filter with a real velocity guess instead of zero removes most of
        the several-frame convergence lag that would otherwise show up as
        a large transient tracking-error spike right after lock is first
        acquired on a fast-moving target -- exactly the ≤10px-while-locked
        requirement's worst case (Section 10)."""
        self.cfg = cfg
        x0 = np.array([init_pos[0], init_pos[1], init_vel[0], init_vel[1], 0.0])
        P0 = np.diag([25.0, 25.0, 100.0, 100.0, 0.05])
        self.models: List[KalmanModel] = [
            KalmanModel("cv", x0.copy(), P0.copy(), cfg.q_cv, is_ct=False),
            KalmanModel("ct", x0.copy(), P0.copy(), cfg.q_ct, is_ct=True),
            KalmanModel("rw", x0.copy(), P0.copy(), cfg.q_rw, is_ct=False),
        ]
        n = len(self.models)
        self.mode_probs = np.ones(n) / n
        # transition probability matrix: high self-persistence, small
        # cross-switch probability (standard IMM Markov-chain design)
        p_stay = 0.92
        self.trans_mat = np.full((n, n), (1 - p_stay) / (n - 1))
        np.fill_diagonal(self.trans_mat, p_stay)
        self.R = np.eye(MEAS_DIM) * cfg.measurement_noise

    @property
    def position(self) -> Tuple[float, float]:
        x, y = 0.0, 0.0
        for m, p in zip(self.models, self.mode_probs):
            x += p * m.x[0]
            y += p * m.x[1]
        return x, y

    @property
    def velocity(self) -> Tuple[float, float]:
        vx, vy = 0.0, 0.0
        for m, p in zip(self.models, self.mode_probs):
            vx += p * m.x[2]
            vy += p * m.x[3]
        return vx, vy

    def _mix(self):
        n = len(self.models)
        c_bar = self.trans_mat.T @ self.mode_probs  # predicted mode probs
        c_bar = np.maximum(c_bar, 1e-12)
        mix_w = np.zeros((n, n))  # mix_w[i,j] = P(model i at t-1 | model j at t)
        for j in range(n):
            for i in range(n):
                mix_w[i, j] = self.trans_mat[i, j] * self.mode_probs[i] / c_bar[j]

        mixed_x = []
        mixed_P = []
        for j in range(n):
            xj = sum(mix_w[i, j] * self.models[i].x for i in range(n))
            Pj = np.zeros((STATE_DIM, STATE_DIM))
            for i in range(n):
                dx = (self.models[i].x - xj).reshape(-1, 1)
                Pj += mix_w[i, j] * (self.models[i].P + dx @ dx.T)
            mixed_x.append(xj)
            mixed_P.append(Pj)
        for j, m in enumerate(self.models):
            m.x = mixed_x[j]
            m.P = mixed_P[j]
        self._c_bar = c_bar

    def step(self, dt: float, measurement: Optional[Tuple[float, float]]):
        self._mix()
        z = np.array(measurement) if measurement is not None else None
        likelihoods = np.zeros(len(self.models))
        for i, m in enumerate(self.models):
            m.predict(dt)
            likelihoods[i] = m.update(z, self.R)
        if measurement is not None:
            new_probs = self._c_bar * likelihoods
            total = new_probs.sum()
            self.mode_probs = new_probs / total if total > 1e-12 else self._c_bar
        else:
            self.mode_probs = self._c_bar  # no measurement: keep predicted mode mix

    def predicted_position_deg_free(self) -> Tuple[float, float]:
        return self.position

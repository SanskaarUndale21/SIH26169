"""Lock-state machine (Section 7.3): searching -> acquiring -> locked ->
reacquiring -> locked / searching."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LockState = Literal["searching", "acquiring", "locked", "reacquiring"]


@dataclass
class LockStateMachine:
    confirm_frames: int = 4          # consecutive detections needed to confirm a lock
    reacquire_timeout_frames: int = 30  # frames spent reacquiring before falling back to searching

    state: LockState = "searching"
    _consecutive_hits: int = 0
    _miss_streak: int = 0
    _reacquire_frames: int = 0

    def update(self, detected: bool) -> LockState:
        if self.state == "searching":
            if detected:
                self._consecutive_hits = 1
                self.state = "acquiring"
            else:
                self._consecutive_hits = 0

        elif self.state == "acquiring":
            if detected:
                self._consecutive_hits += 1
                if self._consecutive_hits >= self.confirm_frames:
                    self.state = "locked"
                    self._miss_streak = 0
            else:
                self._consecutive_hits = 0
                self.state = "searching"

        elif self.state == "locked":
            if detected:
                self._miss_streak = 0
            else:
                self._miss_streak += 1
                if self._miss_streak >= 1:
                    self.state = "reacquiring"
                    self._reacquire_frames = 0

        elif self.state == "reacquiring":
            if detected:
                self.state = "locked"
                self._miss_streak = 0
                self._reacquire_frames = 0
            else:
                self._reacquire_frames += 1
                if self._reacquire_frames >= self.reacquire_timeout_frames:
                    self.state = "searching"
                    self._consecutive_hits = 0
                    self._reacquire_frames = 0

        return self.state

    def reset(self):
        self.state = "searching"
        self._consecutive_hits = 0
        self._miss_streak = 0
        self._reacquire_frames = 0

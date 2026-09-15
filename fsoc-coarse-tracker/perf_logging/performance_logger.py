"""Auto-generates the per-run performance log with the exact fields from
Section 11, in both JSON and CSV. Works identically whether the run was a
Simulator run or a raw-video (Benchmark-2) run.
"""
from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RunMetrics:
    start_time: float = field(default_factory=time.perf_counter)
    frame_count: int = 0
    tracking_errors: List[float] = field(default_factory=list)  # px, only while locked
    locked_frames: int = 0
    post_acquisition_frames: int = 0
    acquisition_time_sec: Optional[float] = None
    frame_process_times_ms: List[float] = field(default_factory=list)
    re_acquisition_events: List[tuple] = field(default_factory=list)  # (start_t, end_t)
    target_loss_events: List[float] = field(default_factory=list)  # timestamps of loss
    _acquired: bool = False
    _reacquiring_since: Optional[float] = None
    _sim_start_t: Optional[float] = None
    _last_t: float = 0.0

    def record_frame(self, timestamp: float, lock_state: str,
                      tracking_error_px: Optional[float], process_time_ms: float):
        if self._sim_start_t is None:
            self._sim_start_t = timestamp
        self.frame_count += 1
        self.frame_process_times_ms.append(process_time_ms)
        self._last_t = timestamp

        if not self._acquired and lock_state == "locked":
            self._acquired = True
            self.acquisition_time_sec = timestamp - self._sim_start_t

        if self._acquired:
            self.post_acquisition_frames += 1
            if lock_state == "locked":
                self.locked_frames += 1
                if tracking_error_px is not None:
                    self.tracking_errors.append(tracking_error_px)
                if self._reacquiring_since is not None:
                    self.re_acquisition_events.append((self._reacquiring_since, timestamp))
                    self._reacquiring_since = None
            elif lock_state == "reacquiring":
                if self._reacquiring_since is None:
                    self._reacquiring_since = timestamp
                    self.target_loss_events.append(timestamp)

    def finalize(self) -> dict:
        wall_duration = time.perf_counter() - self.start_time
        sim_duration = (self._last_t - self._sim_start_t) if self._sim_start_t is not None else 0.0
        fps = self.frame_count / wall_duration if wall_duration > 0 else 0.0
        avg_err = sum(self.tracking_errors) / len(self.tracking_errors) if self.tracking_errors else None
        max_err = max(self.tracking_errors) if self.tracking_errors else None
        rmse = (sum(e ** 2 for e in self.tracking_errors) / len(self.tracking_errors)) ** 0.5 if self.tracking_errors else None
        lock_retention = (self.locked_frames / self.post_acquisition_frames
                           if self.post_acquisition_frames else 0.0)
        avg_proc_ms = (sum(self.frame_process_times_ms) / len(self.frame_process_times_ms)
                       if self.frame_process_times_ms else 0.0)
        reacq_times = [end - start for start, end in self.re_acquisition_events]

        return {
            "simulation_duration_sec": round(sim_duration, 3),
            "fps": round(fps, 2),
            "acquisition_time_sec": round(self.acquisition_time_sec, 3) if self.acquisition_time_sec is not None else None,
            "avg_tracking_error_px": round(avg_err, 3) if avg_err is not None else None,
            "max_tracking_error_px": round(max_err, 3) if max_err is not None else None,
            "lock_retention_rate": round(lock_retention, 4),
            "processing_time_per_frame_ms": round(avg_proc_ms, 3),
            "rmse_px": round(rmse, 3) if rmse is not None else None,
            "re_acquisition_count": len(self.re_acquisition_events),
            "re_acquisition_times_sec": [round(t, 3) for t in reacq_times],
            "target_loss_events": [round(t, 3) for t in self.target_loss_events],
        }


def write_run_log(metrics_dict: dict, output_dir: str, run_name: Optional[str] = None) -> tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    run_name = run_name or time.strftime("run_%Y%m%d_%H%M%S")
    json_path = os.path.join(output_dir, f"{run_name}.json")
    csv_path = os.path.join(output_dir, f"{run_name}.csv")

    with open(json_path, "w") as f:
        json.dump(metrics_dict, f, indent=2)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["field", "value"])
        for k, v in metrics_dict.items():
            writer.writerow([k, v])

    return json_path, csv_path

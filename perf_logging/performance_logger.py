"""Auto-generates the per-run performance log with the exact fields from
Section 11, in both JSON and CSV. Works identically whether the run was a
Simulator run or a raw-video (Benchmark-2) run.

RunMetrics maintains running sums/counts/maxima incrementally in
record_frame() rather than recomputing them from full lists in
finalize() -- finalize() is called every single GUI frame (main_window.py's
step()) for as long as a run is active, so an O(n) full-list scan there
becomes O(n^2) over a multi-minute run: profiled, a naive sum()/max()-based
finalize() grew from ~0.09ms to ~1.8ms per call over a 6000-frame run and
burned ~4s of wall time in aggregate, which is exactly the kind of
self-inflicted per-frame cost that collapses the GUI's real frame rate
over a long session. The raw per-frame lists (tracking_errors etc.) are
kept only for re_acquisition_times_sec/target_loss_events-style small
event lists and are no longer scanned on every finalize() call.
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
    handoff_ready_frames: int = 0
    locked_frames: int = 0
    post_acquisition_frames: int = 0
    acquisition_time_sec: Optional[float] = None
    time_to_handoff_ready_sec: Optional[float] = None
    re_acquisition_events: List[tuple] = field(default_factory=list)  # (start_t, end_t) -- small, bounded by re-acquire count
    target_loss_events: List[float] = field(default_factory=list)  # timestamps of loss -- small, bounded by loss count

    # Running aggregates (updated in O(1) per frame instead of rescanned
    # in finalize()): (sum, count, max) for each locked-frame metric, plus
    # a running sum-of-squares for RMSE.
    _err_sum: float = 0.0
    _err_sq_sum: float = 0.0
    _err_max: float = 0.0
    _err_count: int = 0
    _ang_sum: float = 0.0
    _ang_max: float = 0.0
    _ang_count: int = 0
    _loss_sum: float = 0.0
    _loss_max: float = 0.0
    _loss_count: int = 0
    _proc_sum: float = 0.0
    _proc_count: int = 0
    # raw detected-centroid error vs truth (sub-pixel accuracy of detection
    # itself, independent of the tracker's filtering)
    _cen_sum: float = 0.0
    _cen_max: float = 0.0
    _cen_count: int = 0

    _acquired: bool = False
    _handoff_ready_seen: bool = False
    _reacquiring_since: Optional[float] = None
    _sim_start_t: Optional[float] = None
    _last_t: float = 0.0

    def record_frame(self, timestamp: float, lock_state: str,
                      tracking_error_px: Optional[float], process_time_ms: float,
                      angular_error_urad: Optional[float] = None,
                      link_loss_db: Optional[float] = None,
                      handoff_ready: Optional[bool] = None,
                      centroid_error_px: Optional[float] = None):
        if self._sim_start_t is None:
            self._sim_start_t = timestamp
        self.frame_count += 1
        self._proc_sum += process_time_ms
        self._proc_count += 1
        self._last_t = timestamp
        if centroid_error_px is not None:
            self._cen_sum += centroid_error_px
            self._cen_count += 1
            if centroid_error_px > self._cen_max:
                self._cen_max = centroid_error_px

        if not self._acquired and lock_state == "locked":
            self._acquired = True
            self.acquisition_time_sec = timestamp - self._sim_start_t

        if self._acquired:
            self.post_acquisition_frames += 1
            if lock_state == "locked":
                self.locked_frames += 1
                if tracking_error_px is not None:
                    self._err_sum += tracking_error_px
                    self._err_sq_sum += tracking_error_px * tracking_error_px
                    self._err_count += 1
                    if tracking_error_px > self._err_max:
                        self._err_max = tracking_error_px
                if angular_error_urad is not None:
                    self._ang_sum += angular_error_urad
                    self._ang_count += 1
                    if angular_error_urad > self._ang_max:
                        self._ang_max = angular_error_urad
                if link_loss_db is not None:
                    self._loss_sum += link_loss_db
                    self._loss_count += 1
                    if link_loss_db > self._loss_max:
                        self._loss_max = link_loss_db
                if handoff_ready:
                    self.handoff_ready_frames += 1
                    if not self._handoff_ready_seen:
                        self._handoff_ready_seen = True
                        self.time_to_handoff_ready_sec = timestamp - self._sim_start_t
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

        avg_err = self._err_sum / self._err_count if self._err_count else None
        max_err = self._err_max if self._err_count else None
        rmse = (self._err_sq_sum / self._err_count) ** 0.5 if self._err_count else None
        lock_retention = (self.locked_frames / self.post_acquisition_frames
                           if self.post_acquisition_frames else 0.0)
        avg_proc_ms = self._proc_sum / self._proc_count if self._proc_count else 0.0
        reacq_times = [end - start for start, end in self.re_acquisition_events]

        avg_ang = self._ang_sum / self._ang_count if self._ang_count else None
        max_ang = self._ang_max if self._ang_count else None
        avg_loss = self._loss_sum / self._loss_count if self._loss_count else None
        max_loss = self._loss_max if self._loss_count else None
        handoff_ready_rate = (self.handoff_ready_frames / self.locked_frames
                               if self.locked_frames else 0.0)

        return {
            "simulation_duration_sec": round(sim_duration, 3),
            "fps": round(fps, 2),
            "acquisition_time_sec": round(self.acquisition_time_sec, 3) if self.acquisition_time_sec is not None else None,
            "avg_tracking_error_px": round(avg_err, 3) if avg_err is not None else None,
            "max_tracking_error_px": round(max_err, 3) if max_err is not None else None,
            "lock_retention_rate": round(lock_retention, 4),
            "processing_time_per_frame_ms": round(avg_proc_ms, 3),
            "rmse_px": round(rmse, 3) if rmse is not None else None,
            "avg_centroid_error_px": round(self._cen_sum / self._cen_count, 4) if self._cen_count else None,
            "max_centroid_error_px": round(self._cen_max, 4) if self._cen_count else None,
            "re_acquisition_count": len(self.re_acquisition_events),
            "re_acquisition_times_sec": [round(t, 3) for t in reacq_times],
            "target_loss_events": [round(t, 3) for t in self.target_loss_events],
            # Link-budget-relevant additions (see simulator/link_budget.py):
            "avg_angular_error_urad": round(avg_ang, 3) if avg_ang is not None else None,
            "max_angular_error_urad": round(max_ang, 3) if max_ang is not None else None,
            "avg_pointing_loss_db": round(avg_loss, 4) if avg_loss is not None else None,
            "max_pointing_loss_db": round(max_loss, 4) if max_loss is not None else None,
            "handoff_ready_rate": round(handoff_ready_rate, 4),
            "time_to_handoff_ready_sec": round(self.time_to_handoff_ready_sec, 3) if self.time_to_handoff_ready_sec is not None else None,
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

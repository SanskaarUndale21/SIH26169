"""Web console API: pages render, preview renders a real frame, a live
run streams and auto-saves its log (including when the source ends on
its own), and the centroid CSV is built from the saved frame log."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

import web.dashboard_server as server  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "LOGS_DIR", tmp_path)
    return TestClient(server.app)


def test_every_page_renders_with_nav(client):
    for path in ("/", "/setup", "/live", "/runs", "/spec", "/runs/run_x"):
        r = client.get(path)
        assert r.status_code == 200
        assert 'class="sidebar"' in r.text and "<!--SIDEBAR-->" not in r.text


def test_old_urls_redirect(client):
    assert client.get("/control", follow_redirects=False).status_code in (302, 307)


def test_preview_renders_frame_and_path(client):
    r = client.post("/api/preview", json={"ui_values": {"target/motion": "sinusoidal",
                                                           "disturbances/noise/gaussian/enabled": True}})
    assert r.status_code == 200
    d = r.json()
    assert d["image"].startswith("data:image/jpeg;base64,")
    assert len(d["paths"]) == 1 and len(d["paths"][0]) > 100


def test_preview_rejects_bad_waypoints(client):
    r = client.post("/api/preview", json={"ui_values": {"target/motion": "user_defined",
                                                           "target/motion_params/user_defined/waypoints": "1,2,3"}})
    assert r.status_code == 400


def test_run_autosaves_and_exports_centroids(client, tmp_path):
    r = client.post("/api/control/start", json={"ui_values": {}, "realtime": False})
    assert r.status_code == 200
    name = r.json()["run_name"]
    time.sleep(1.0)
    stop = client.post("/api/control/stop").json()
    assert stop["metrics"]["acquisition_time_sec"] is not None
    assert (tmp_path / f"{name}.json").exists()
    assert (tmp_path / f"{name}_config.json").exists()
    runs = client.get("/api/runs").json()
    assert runs[0]["name"] == name and runs[0]["info"]["mode"] == "simulator"
    csv_text = client.get(f"/api/runs/{name}/centroids.csv").text
    header, first = csv_text.splitlines()[:2]
    assert header.startswith("frame_id,timestamp_s,lock_state")
    assert len(first.split(",")) == 12


def test_simultaneous_starts_launch_exactly_one_run(client):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda _: client.post("/api/control/start", json={"ui_values": {}, "realtime": True}).status_code, range(8)))
    client.post("/api/control/stop")
    assert sorted(codes) == [200] + [409] * 7


def test_unknown_algorithm_is_a_bad_request(client):
    r = client.post("/api/control/start", json={"ui_values": {"algorithms/tracker/id": "user:nope:X"}})
    assert r.status_code == 400 and "not found" in r.json()["detail"]

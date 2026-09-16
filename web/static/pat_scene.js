// Shared Three.js PAT (pointing-acquisition-tracking) scene: used
// identically by the static replay page (/view/{name}) and the live
// control page (/control), so both draw the exact same geometry from
// the exact same math -- one implementation, not two that could drift.
//
// Every number this module draws comes from a real FrameRecord (see
// perf_logging/frame_log.py): cam_pan_deg/cam_tilt_deg from the actual
// CameraModel state, ground_truth_px from the simulator's real target
// position, predicted_px from the tracker's real IMM output. The only
// invented convention is DISPLAY_RANGE -- a fixed distance used to turn
// pure angles into a 3D point, since this simulator is 2D and does not
// model true range.
import * as THREE from "three";
import { OrbitControls } from "/static/OrbitControls.js";

export const DISPLAY_RANGE = 400;
export const LOCK_COLORS = {
  searching: 0xef4444, acquiring: 0xeab308, reacquiring: 0xeab308, locked: 0x22c55e,
};

export function anglesToPoint(panDeg, tiltDeg, range = DISPLAY_RANGE) {
  const pan = panDeg * Math.PI / 180, tilt = tiltDeg * Math.PI / 180;
  return new THREE.Vector3(range * Math.tan(pan), range * Math.tan(tilt), range);
}

export function createPATScene(holderElement) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(holderElement.clientWidth, holderElement.clientHeight);
  holderElement.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0b0f);
  const camera3 = new THREE.PerspectiveCamera(
    55, holderElement.clientWidth / holderElement.clientHeight, 1, 5000);
  camera3.position.set(500, 350, -500);
  camera3.lookAt(0, 0, DISPLAY_RANGE);

  const controls = new OrbitControls(camera3, renderer.domElement);
  controls.target.set(0, 0, DISPLAY_RANGE * 0.5);
  controls.update();

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
  dirLight.position.set(200, 400, -200);
  scene.add(dirLight);

  const grid = new THREE.GridHelper(800, 16, 0x334155, 0x1e293b);
  grid.rotation.x = Math.PI / 2;
  grid.position.z = DISPLAY_RANGE;
  scene.add(grid);
  scene.add(new THREE.AxesHelper(150));

  const coneGeo = new THREE.ConeGeometry(40, DISPLAY_RANGE * 0.9, 24, 1, true);
  coneGeo.rotateX(Math.PI / 2);
  coneGeo.translate(0, 0, DISPLAY_RANGE * 0.45);
  const coneMat = new THREE.MeshStandardMaterial({
    color: 0x3b82f6, transparent: true, opacity: 0.35, side: THREE.DoubleSide,
  });
  const coneMesh = new THREE.Mesh(coneGeo, coneMat);
  scene.add(coneMesh);

  const gtMesh = new THREE.Mesh(
    new THREE.SphereGeometry(9, 16, 16), new THREE.MeshStandardMaterial({ color: 0x4ade80 }));
  scene.add(gtMesh);

  const beliefMesh = new THREE.Mesh(
    new THREE.SphereGeometry(7, 16, 16), new THREE.MeshStandardMaterial({ color: 0xfacc15 }));
  scene.add(beliefMesh);

  const MAX_TRAIL = 400;
  function makeTrail(color) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(MAX_TRAIL * 3), 3));
    const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.5 });
    const line = new THREE.Line(geo, mat);
    line.userData.points = [];
    scene.add(line);
    return line;
  }
  const targetTrail = makeTrail(0x4ade80);
  const camTrail = makeTrail(0x3b82f6);

  function pushTrail(line, point) {
    const pts = line.userData.points;
    pts.push(point.clone());
    if (pts.length > MAX_TRAIL) pts.shift();
    const pos = line.geometry.attributes.position;
    for (let i = 0; i < pts.length; i++) pos.setXYZ(i, pts[i].x, pts[i].y, pts[i].z);
    line.geometry.setDrawRange(0, pts.length);
    pos.needsUpdate = true;
  }

  function resetTrails() {
    targetTrail.userData.points = [];
    camTrail.userData.points = [];
    targetTrail.geometry.setDrawRange(0, 0);
    camTrail.geometry.setDrawRange(0, 0);
  }

  function applyFrame(rec) {
    if (rec.cam_pan_deg == null || rec.cam_tilt_deg == null) return null;
    const camPt = anglesToPoint(rec.cam_pan_deg, rec.cam_tilt_deg);
    coneMesh.position.set(0, 0, 0);
    coneMesh.lookAt(camPt);
    coneMat.color.setHex(LOCK_COLORS[rec.lock_state] || 0x888888);
    pushTrail(camTrail, camPt);

    const fov = rec.fov_deg || [4.0, 3.0];
    const pxPerDegX = 640 / fov[0], pxPerDegY = 480 / fov[1];

    let angularErrorPx = null;
    if (rec.ground_truth_px && rec.ground_truth_px.length > 0) {
      const [gx, gy] = rec.ground_truth_px[0];
      const tPan = rec.cam_pan_deg + (gx - 320) / pxPerDegX;
      const tTilt = rec.cam_tilt_deg + (gy - 240) / pxPerDegY;
      const tPt = anglesToPoint(tPan, tTilt);
      gtMesh.position.copy(tPt);
      gtMesh.visible = true;
      pushTrail(targetTrail, tPt);
      if (rec.predicted_px) {
        const [px, py] = rec.predicted_px;
        angularErrorPx = Math.hypot(px - gx, py - gy);
      }
    } else {
      gtMesh.visible = false;
    }

    if (rec.predicted_px) {
      const [px, py] = rec.predicted_px;
      const bPan = rec.cam_pan_deg + (px - 320) / pxPerDegX;
      const bTilt = rec.cam_tilt_deg + (py - 240) / pxPerDegY;
      beliefMesh.position.copy(anglesToPoint(bPan, bTilt));
    }
    return { trackingErrorPx: angularErrorPx };
  }

  function onResize() {
    renderer.setSize(holderElement.clientWidth, holderElement.clientHeight);
    camera3.aspect = holderElement.clientWidth / holderElement.clientHeight;
    camera3.updateProjectionMatrix();
  }
  window.addEventListener("resize", onResize);

  function startRenderLoop() {
    function tick() {
      requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera3);
    }
    tick();
  }

  return { applyFrame, resetTrails, startRenderLoop, renderer, scene, camera3 };
}

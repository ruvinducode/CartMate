#!/usr/bin/env python3
"""
CartMate Lightweight Real-Time Web Visualizer
Provides an interactive 2D HUD Dashboard on port 8080 for remote Mac/Phone browsers:
  - '/' or '/index.html': Live 2D LiDAR Environment Map, Cart Pose, and Shelf Display
  - '/commands' or '/navigation': Dedicated Navigation Cockpit showing live estimated commands,
    steering dial, heading error, distance countdown, mission timeline, and live decision logs.
"""

import http.server
import socketserver
import threading
import json
import os
import time

# ==============================================================================
# 1. MAIN HUD: 2D LiDAR Map & Product Shelf HUD (Served at '/')
# ==============================================================================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🛒 CartMate Navigation HUD</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Outfit:wght@300;400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #070c18;
      --surface: rgba(12,20,38,0.9);
      --border: rgba(255,255,255,0.07);
      --cyan: #00f2fe;
      --green: #11998e;
      --green-bright: #38ef7d;
      --red: #ff3366;
      --amber: #ffb703;
      --purple: #a855f7;
      --text: #e2e8f0;
      --text-dim: #64748b;
    }
    * { box-sizing: border-box; margin:0; padding:0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Outfit', sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    /* --- HEADER --- */
    header {
      background: rgba(7,12,24,0.97);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky; top:0; z-index:200;
      backdrop-filter: blur(16px);
    }
    .logo { display:flex; align-items:center; gap:12px; }
    .logo-icon {
      width: 38px; height: 38px; border-radius: 10px;
      background: linear-gradient(135deg,#4facfe,#00f2fe);
      display:flex; align-items:center; justify-content:center;
      font-size:20px;
      box-shadow: 0 0 18px rgba(0,242,254,0.35);
    }
    .logo h1 { font-size:1.1rem; font-weight:700; letter-spacing:-.5px; }
    .logo p { font-size:.7rem; color:var(--text-dim); }
    .pills { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    .cockpit-link-btn {
      font-family: 'JetBrains Mono', monospace;
      font-size: .75rem;
      font-weight: 700;
      padding: 5px 13px;
      border-radius: 20px;
      text-decoration: none;
      color: #00f2fe;
      background: rgba(0,242,254,0.12);
      border: 1px solid rgba(0,242,254,0.45);
      transition: all .2s;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .cockpit-link-btn:hover {
      background: rgba(0,242,254,0.25);
      box-shadow: 0 0 16px rgba(0,242,254,0.35);
      color: #fff;
    }
    .pill {
      font-family: 'JetBrains Mono',monospace;
      font-size:.72rem; padding:4px 11px; border-radius:20px;
      display:flex; align-items:center; gap:5px;
      border: 1px solid rgba(56,239,125,.3);
      background: rgba(56,239,125,.08);
      color: var(--green-bright);
    }
    .pulse { width:7px;height:7px;border-radius:50%;background:var(--green-bright);
      box-shadow:0 0 8px var(--green-bright); animation:pulse 1.4s infinite; }
    @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.35;transform:scale(.8)} }

    /* --- LAYOUT --- */
    .app { display:grid; grid-template-columns:1fr 360px; gap:16px; padding:16px; flex:1; min-height:0; }
    @media(max-width:900px){ .app { grid-template-columns:1fr; } }

    /* --- MAP PANEL --- */
    .map-panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 18px;
      position: relative;
      overflow: hidden;
      height: calc(100vh - 84px);
      display:flex; flex-direction:column;
    }
    .map-toolbar {
      display:flex; justify-content:space-between; align-items:center;
      padding: 10px 16px;
      border-bottom: 1px solid var(--border);
      background: rgba(0,0,0,.15);
      flex-shrink: 0;
    }
    .map-title { font-size:.8rem; font-weight:600; color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; }
    .map-tags { display:flex; gap:8px; align-items:center; }
    .mtag {
      font-family: 'JetBrains Mono', monospace;
      font-size:.7rem; padding:3px 9px; border-radius:5px;
      background: rgba(255,255,255,.05); border:1px solid var(--border);
    }
    #canvas-wrap { flex:1; position:relative; min-height:0; }
    canvas { position:absolute; top:0; left:0; width:100%; height:100%; cursor:crosshair; }

    /* --- CANCEL BUTTON BAR --- */
    #cancel-wrap {
      display: none;
      flex-shrink: 0;
      padding: 12px 16px;
      border-top: 1px solid var(--border);
      background: rgba(255,51,102,0.06);
    }
    #cancel-btn {
      width: 100%;
      padding: 11px 0;
      background: rgba(255,51,102,0.16);
      border: 1.5px solid var(--red);
      border-radius: 11px;
      color: var(--red);
      font-family: 'JetBrains Mono', monospace;
      font-size: .92rem;
      font-weight: 700;
      letter-spacing: 1px;
      cursor: pointer;
      transition: all .25s;
      text-shadow: 0 0 10px rgba(255,51,102,.3);
    }
    #cancel-btn:hover {
      background: rgba(255,51,102,0.32);
      box-shadow: 0 0 20px rgba(255,51,102,.3);
    }

    /* --- SIDEBAR --- */
    .sidebar { display:flex; flex-direction:column; gap:14px; overflow-y:auto; height:calc(100vh - 84px); }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      flex-shrink: 0;
    }
    .card-head {
      font-size:.75rem; text-transform:uppercase; letter-spacing:1.2px;
      color:var(--text-dim); font-weight:600; margin-bottom:14px;
      display:flex; justify-content:space-between; align-items:center;
    }
    .badge-count {
      background: rgba(255,255,255,.08);
      font-family:'JetBrains Mono',monospace;
      font-size:.65rem; padding:2px 7px; border-radius:99px;
      color: var(--text-dim);
    }

    /* --- ACTION BADGE --- */
    .action-badge {
      font-family:'JetBrains Mono',monospace; font-size:1.05rem; font-weight:800;
      text-align:center; padding:13px; border-radius:11px; letter-spacing:1px;
      background: rgba(0,242,254,.08); border:1px solid var(--cyan); color:var(--cyan);
      text-shadow: 0 0 10px rgba(0,242,254,.4);
      transition: all .3s;
    }
    .action-badge.stop { background:rgba(255,51,102,.12); border-color:var(--red); color:var(--red); text-shadow:0 0 14px rgba(255,51,102,.5); }
    .action-badge.reached { background:rgba(56,239,125,.12); border-color:var(--green-bright); color:var(--green-bright); }
    .action-badge.waiting { border-color:var(--text-dim); color:var(--text-dim); background:rgba(255,255,255,.03); }
    .action-badge.cancelled { background:rgba(255,183,3,.12); border-color:var(--amber); color:var(--amber); text-shadow:0 0 10px rgba(255,183,3,.4); }

    /* --- STATS --- */
    .stat { display:flex; justify-content:space-between; align-items:baseline; padding:7px 0; border-bottom:1px solid rgba(255,255,255,.04); }
    .stat:last-child { border-bottom:none; }
    .sl { font-size:.82rem; color:var(--text-dim); }
    .sv { font-family:'JetBrains Mono',monospace; font-size:.92rem; font-weight:600; }

    /* --- PRODUCT SHELF LIST --- */
    .shelf-list { display:flex; flex-direction:column; gap:10px; max-height:300px; overflow-y:auto; }
    .shelf-card {
      background: rgba(255,255,255,.03);
      border: 1px solid rgba(255,255,255,.07);
      border-radius: 12px;
      padding: 11px 13px;
      transition: all .25s;
    }
    .shelf-card.active {
      border-color: var(--red);
      background: rgba(255,51,102,.07);
      box-shadow: 0 0 12px rgba(255,51,102,.15);
    }
    .shelf-card.reached {
      border-color: rgba(56,239,125,.3);
      background: rgba(56,239,125,.05);
    }
    .shelf-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }
    .shelf-name { font-weight:700; font-size:.88rem; }
    .shelf-status {
      font-family:'JetBrains Mono',monospace; font-size:.68rem;
      padding:2px 8px; border-radius:99px;
      background: rgba(255,255,255,.07);
    }
    .shelf-coord { font-family:'JetBrains Mono',monospace; font-size:.72rem; color:var(--text-dim); margin-bottom:8px; }

    .product-tags { display:flex; flex-wrap:wrap; gap:5px; }
    .product-tag {
      font-size:.72rem; padding:3px 9px; border-radius:99px;
      border: 1px solid rgba(168,85,247,.4);
      background: rgba(168,85,247,.08);
      color: #c084fc;
      display:flex; align-items:center; gap:4px;
    }
    .product-tag.found {
      border-color: rgba(56,239,125,.4);
      background: rgba(56,239,125,.08);
      color: var(--green-bright);
    }

    .lidar-bar-wrap { margin-top:8px; }
    .lidar-bar-label { display:flex; justify-content:space-between; font-size:.7rem; color:var(--text-dim); margin-bottom:3px; }
    .lidar-bar { height:4px; border-radius:4px; background:rgba(255,255,255,.07); overflow:hidden; }
    .lidar-bar-fill { height:100%; border-radius:4px; transition:width .5s; }

    /* --- LEGEND --- */
    .legend { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
    .leg { display:flex; align-items:center; gap:5px; font-size:.72rem; color:var(--text-dim); }
    .leg-dot { width:9px;height:9px;border-radius:50%; }
    .leg-sq { width:9px;height:9px;border-radius:2px; }

    .dl-btn {
      display:block; text-align:center; margin-top:12px;
      background:rgba(255,255,255,.04); color:var(--text);
      text-decoration:none; padding:9px; border-radius:9px;
      font-size:.8rem; font-weight:600; border:1px solid var(--border);
      transition:background .2s;
    }
    .dl-btn:hover { background:rgba(255,255,255,.09); }
  </style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">🛒</div>
    <div>
      <h1>CartMate Navigation HUD</h1>
      <p>Live 2D LiDAR Map · Product Location Estimation</p>
    </div>
  </div>
  <div class="pills">
    <a href="/commands" target="_blank" class="cockpit-link-btn">🧭 Open Navigation Command View ↗</a>
    <div class="pill"><div class="pulse"></div><span id="conn-text">Connecting...</span></div>
    <div class="pill" style="border-color:rgba(0,242,254,.3);background:rgba(0,242,254,.06);color:var(--cyan);" id="pts-pill">⚡ 0 pts</div>
  </div>
</header>

<div class="app">
  <!-- 2D MAP CANVAS -->
  <div class="map-panel">
    <div class="map-toolbar">
      <span class="map-title">🗺️ Live 2D LiDAR Environment Map</span>
      <div class="map-tags">
        <button onclick="resetView()" class="mtag" style="cursor:pointer;background:rgba(0,242,254,0.15);border-color:var(--cyan);color:var(--cyan);font-weight:700;">🎯 Reset / Center View</button>
        <span class="mtag" id="goal-tag">Goal: –</span>
        <span class="mtag" id="lidar-pts-tag">0 scan pts</span>
        <span class="mtag" id="zoom-tag">Zoom: 1.0x (Scroll/Drag)</span>
      </div>
    </div>
    <div id="canvas-wrap">
      <canvas id="lidarCanvas"></canvas>
    </div>
    <!-- Cancel Navigation Button (visible during active orders) -->
    <div id="cancel-wrap">
      <button id="cancel-btn" onclick="cancelNavigation()">⛔ CANCEL NAVIGATION (CLEAR SHELF)</button>
    </div>
  </div>

  <!-- SIDEBAR -->
  <div class="sidebar">

    <!-- Steering & Nav -->
    <div class="card">
      <div class="card-head">Steering Command</div>
      <div class="action-badge waiting" id="cmd-badge">WAITING FOR APP</div>
      <div style="margin-top:13px;">
        <div class="stat"><span class="sl">Distance to Goal</span><span class="sv" id="v-dist">0.00 m</span></div>
        <div class="stat"><span class="sl">Heading Error</span><span class="sv" id="v-angle">0.00°</span></div>
        <div class="stat"><span class="sl">Front Obstacle</span><span class="sv" id="v-obs" style="color:var(--green-bright)">Clear</span></div>
      </div>
    </div>

    <!-- Cart Pose -->
    <div class="card">
      <div class="card-head">Cart Pose <span class="badge-count">Odometry</span></div>
      <div class="stat"><span class="sl">X</span><span class="sv" id="v-cx">0.00 m</span></div>
      <div class="stat"><span class="sl">Y</span><span class="sv" id="v-cy">0.00 m</span></div>
      <div class="stat"><span class="sl">Theta</span><span class="sv" id="v-th">0.0°</span></div>
    </div>

    <!-- Product Location Estimation -->
    <div class="card">
      <div class="card-head">
        🛍️ Product Locations
        <span class="badge-count" id="shelf-badge">0 shelves</span>
      </div>
      <div class="shelf-list" id="shelf-list">
        <div style="color:var(--text-dim);font-size:.83rem;text-align:center;padding:16px 0;">
          Send an order from the App to see product locations on the map
        </div>
      </div>
      <div class="legend">
        <div class="leg"><div class="leg-dot" style="background:#ff5366"></div>Obstacle &lt;0.6m</div>
        <div class="leg"><div class="leg-dot" style="background:#ffb703"></div>Caution 0.6-1.5m</div>
        <div class="leg"><div class="leg-dot" style="background:#00f2fe"></div>LiDAR Scan</div>
        <div class="leg"><div class="leg-dot" style="background:#38ef7d"></div>Cart (Robot)</div>
        <div class="leg"><div class="leg-sq" style="background:#ff3366"></div>Active Target</div>
        <div class="leg"><div class="leg-sq" style="background:#ffb703"></div>Queued Shelf</div>
        <div class="leg"><div class="leg-dot" style="background:rgba(56,239,125,.3);border:1px solid #38ef7d"></div>LiDAR Confirmed</div>
      </div>
      <a href="/map.png" target="_blank" class="dl-btn">🖼️ Download Hi-Res Map PNG</a>
      <a href="/commands" target="_blank" class="dl-btn" style="border-color:rgba(0,242,254,0.4);color:var(--cyan);margin-top:8px;">🧭 Open Cockpit View in New Tab</a>
    </div>

  </div>
</div>

<script>
  const canvas = document.getElementById('lidarCanvas');
  const ctx    = canvas.getContext('2d');
  const wrap   = document.getElementById('canvas-wrap');

  function resizeCanvas() {
    canvas.width  = wrap.clientWidth  || wrap.offsetWidth  || 600;
    canvas.height = wrap.clientHeight || wrap.offsetHeight || 540;
  }
  window.addEventListener('resize', resizeCanvas);
  setTimeout(resizeCanvas, 120);

  let zoom = 1.0;
  let panX = 0;
  let panY = 0;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;

  const BASE_SCALE = 45; // 45px per meter default: 12m visible on 540px canvas

  canvas.addEventListener('mousedown', e => {
    isDragging = true;
    dragStartX = e.clientX - panX;
    dragStartY = e.clientY - panY;
  });
  window.addEventListener('mousemove', e => {
    if (isDragging) {
      panX = e.clientX - dragStartX;
      panY = e.clientY - dragStartY;
    }
  });
  window.addEventListener('mouseup', () => { isDragging = false; });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 0.87;
    zoom = Math.max(0.4, Math.min(zoom * factor, 3.5));
  }, { passive: false });

  function resetView() {
    zoom = 1.0;
    panX = 0;
    panY = 0;
  }

  function ptColour(dist) {
    if (dist <= 0.85) return 'rgba(255,51,102,0.95)';  // Danger Obstacle/Wall (Red)
    if (dist <= 1.8)  return 'rgba(255,183,3,0.85)';   // Caution Zone (Amber)
    return 'rgba(0,242,254,0.7)';                      // Clear Wall / Perimeter (Cyan)
  }

  function clusterNearby(pts, wx, wy, radius) {
    const r2 = radius * radius;
    return pts.filter(p => (p[0]-wx)**2 + (p[1]-wy)**2 <= r2).length;
  }

  function drawRadarGrid(cx, cy, currentScale) {
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    for (let r = 1; r <= 8; r++) {
      ctx.beginPath();
      ctx.arc(cx, cy, r * currentScale, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#475569';
      ctx.font = '10px JetBrains Mono,monospace';
      ctx.fillText(r + 'm', cx + r * currentScale + 4, cy - 4);
    }
    ctx.strokeStyle = 'rgba(255,255,255,0.07)';
    ctx.beginPath(); ctx.moveTo(0, cy); ctx.lineTo(canvas.width, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, canvas.height); ctx.stroke();
  }

  function drawShelf(cx, cy, wx, wy, wp, isActive, isDone, clusteredPts, currentScale) {
    const sx = cx + (wx - pose.x) * currentScale;
    const sy = cy - (wy - pose.y) * currentScale;

    // Glowing radius when confirmed by LiDAR
    if (clusteredPts >= 4) {
      const radius = Math.min(26 + clusteredPts * 1.5, 55);
      const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, radius);
      grad.addColorStop(0, 'rgba(56,239,125,0.25)');
      grad.addColorStop(1, 'rgba(56,239,125,0)');
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.arc(sx, sy, radius, 0, Math.PI*2); ctx.fill();
    }

    // Active trajectory guide line from Cart to target
    if (isActive) {
      ctx.save();
      ctx.setLineDash([8, 5]);
      ctx.strokeStyle = 'rgba(255,51,102,0.85)';
      ctx.lineWidth = 2.2;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(sx, sy); ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
    }

    // Beacon marker
    const color = isDone ? '#38ef7d' : (isActive ? '#ff3366' : '#ffb703');
    const size = isActive ? 16 : 12;

    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = isActive ? 18 : 8;
    ctx.fillRect(sx - size/2, sy - size/2, size, size);
    ctx.shadowBlur = 0;

    // Target Label (e.g. SHELF_C (5.2m, 4.1m))
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 12px Outfit, sans-serif';
    ctx.fillText(`${wp.shelf_id || 'Shelf'} (${wx.toFixed(1)}m, ${wy.toFixed(1)}m)`, sx + size/2 + 6, sy + 4);

    const items = wp.items || [];
    if (items.length) {
      ctx.fillStyle = '#c084fc';
      ctx.font = '10px Outfit, sans-serif';
      ctx.fillText(items.join(' · '), sx + size/2 + 6, sy + 18);
    }

    if (clusteredPts >= 4) {
      ctx.fillStyle = '#38ef7d';
      ctx.font = 'bold 9px Outfit, sans-serif';
      ctx.fillText(`✓ LiDAR Confirmed (${clusteredPts} pts)`, sx + size/2 + 6, sy + 30);
    }
  }

  function drawCart(cx, cy, thetaRad) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-thetaRad); // Standard Cartesian: 0° is along +X (Right)

    ctx.shadowColor = '#38ef7d';
    ctx.shadowBlur = 18;
    ctx.fillStyle = '#38ef7d';
    ctx.beginPath(); ctx.arc(0, 0, 13, 0, Math.PI*2); ctx.fill();
    ctx.shadowBlur = 0;

    // Forward direction arrow pointing along +X (Right)
    ctx.fillStyle = '#070c18';
    ctx.beginPath();
    ctx.moveTo(16, 0); ctx.lineTo(6, -6); ctx.lineTo(6, 6);
    ctx.closePath(); ctx.fill();

    ctx.restore();
  }

  let pose = { x:0, y:0, theta:0 };
  let cancelled = false;
  let lastOrderId = null;

  async function cancelNavigation() {
    try {
      await fetch('/api/cancel', { method: 'POST' });
    } catch(e) {}
    cancelled = true;
    document.getElementById('cancel-wrap').style.display = 'none';

    const badge = document.getElementById('cmd-badge');
    badge.textContent = 'NAVIGATION CANCELLED';
    badge.className = 'action-badge cancelled';
    document.getElementById('goal-tag').textContent = 'Goal: Cancelled ⛔';

    // Clear shelves on the client immediately!
    document.getElementById('shelf-badge').textContent = '0 shelves';
    document.getElementById('shelf-list').innerHTML = `
      <div style="color:var(--amber);font-size:.85rem;text-align:center;padding:16px 0;line-height:1.5;">
        ⛔ Navigation Cancelled.<br>
        <span style="color:var(--text-dim);font-size:.75rem;">Shelves removed from Map. Waiting for next order.</span>
      </div>`;

    // Redraw map with ZERO shelves
    renderScene({
      cart_pose: pose,
      lidar_points: latestPoints,
      waypoints: [],
      active_waypoint_index: 0,
      current_action: 'CANCELLED',
      distance_to_target: 0,
      angle_error: 0,
      is_blocked: false,
      min_obstacle_dist: 0
    });
  }

  let latestPoints = [];

  function renderScene(data) {
    if (canvas.width < 10 || canvas.height < 10) resizeCanvas();

    pose = data.cart_pose || { x:0, y:0, theta:0 };
    const points    = data.lidar_points || [];
    latestPoints    = points;
    // When cancelled, waypoints are explicitly suppressed so NO shelves are shown!
    const waypoints = cancelled ? [] : (data.waypoints || []);
    const activeIdx = data.active_waypoint_index ?? 0;
    const action    = data.current_action || 'IDLE';
    const thetaRad  = pose.theta * Math.PI / 180;

    const currentScale = BASE_SCALE * zoom;
    const cx = (canvas.width  / 2) + panX;
    const cy = (canvas.height / 2) + panY;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawRadarGrid(cx, cy, currentScale);

    // 1. Forward Safety Arc along Cart heading
    const sa = -thetaRad - (50 * Math.PI / 180);
    const ea = -thetaRad + (50 * Math.PI / 180);
    ctx.beginPath(); ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, 1.2 * currentScale, sa, ea); ctx.closePath();
    ctx.fillStyle = data.is_blocked ? 'rgba(255,51,102,0.3)' : 'rgba(56,239,125,0.06)';
    ctx.fill();

    // 2. LiDAR point cloud (Obstacles & Walls)
    for (let pt of points) {
      const px   = cx + (pt[0] - pose.x) * currentScale;
      const py   = cy - (pt[1] - pose.y) * currentScale;
      const dist = Math.hypot(pt[0] - pose.x, pt[1] - pose.y);
      ctx.fillStyle = ptColour(dist);
      const dotSize = dist <= 0.85 ? 5 : 3.5;
      ctx.fillRect(px - dotSize/2, py - dotSize/2, dotSize, dotSize);
    }

    // 3. Shelves (only drawn if NOT cancelled and waypoints exist)
    const clusterResults = [];
    if (!cancelled) {
      waypoints.forEach((wp, idx) => {
        const wx = wp.target_x ?? wp.x ?? 0;
        const wy = wp.target_y ?? wp.y ?? 0;
        const isActive = (idx === activeIdx);
        const isDone   = idx < activeIdx;
        const nPts = clusterNearby(points, wx, wy, 0.75);
        clusterResults.push(nPts);
        drawShelf(cx, cy, wx, wy, wp, isActive, isDone, nPts, currentScale);
      });
    }

    // 4. Cart
    drawCart(cx, cy, thetaRad);

    // 5. Warning banner if blocked
    if (data.is_blocked) {
      ctx.fillStyle = 'rgba(255,51,102,0.85)';
      ctx.font = 'bold 13px JetBrains Mono, monospace';
      ctx.fillText(`🚨 WALL / OBSTACLE DETECTED (${(data.min_obstacle_dist ?? 0).toFixed(2)}m)`, 16, 28);
    }

    // UI updates
    document.getElementById('conn-text').textContent = 'Pi 5 Connected';
    document.getElementById('pts-pill').textContent  = `⚡ ${points.length} pts`;
    document.getElementById('lidar-pts-tag').textContent = points.length + ' scan pts';
    const zoomTag = document.getElementById('zoom-tag');
    if (zoomTag) zoomTag.textContent = `Zoom: ${zoom.toFixed(1)}x`;

    const badge = document.getElementById('cmd-badge');
    if (cancelled) {
      badge.textContent = 'NAVIGATION CANCELLED';
      badge.className   = 'action-badge cancelled';
      document.getElementById('goal-tag').textContent = 'Goal: Cancelled ⛔';
    } else {
      badge.textContent  = action;
      badge.className    = 'action-badge';
      if (action.includes('STOP'))        badge.classList.add('stop');
      else if (action.includes('REACHED')) badge.classList.add('reached');
      else if (action.includes('WAIT'))    badge.classList.add('waiting');

      if (waypoints.length) {
        const aw = waypoints[activeIdx];
        document.getElementById('goal-tag').textContent =
          aw ? `Goal [${activeIdx+1}/${waypoints.length}] ${aw.shelf_id}` : 'All Done ✅';
      } else {
        document.getElementById('goal-tag').textContent = 'Goal: Waiting...';
      }
    }

    document.getElementById('v-dist').textContent  = (data.distance_to_target ?? 0).toFixed(2) + ' m';
    document.getElementById('v-angle').textContent = (data.angle_error ?? 0).toFixed(2) + '°';
    document.getElementById('v-cx').textContent    = (pose.x).toFixed(2) + ' m';
    document.getElementById('v-cy').textContent    = (pose.y).toFixed(2) + ' m';
    document.getElementById('v-th').textContent    = (pose.theta).toFixed(1) + '°';

    const obsEl = document.getElementById('v-obs');
    if (data.is_blocked) {
      obsEl.textContent = 'BLOCKED ' + (data.min_obstacle_dist ?? 0).toFixed(2) + 'm';
      obsEl.style.color = 'var(--red)';
    } else {
      obsEl.textContent = 'Clear ' + (data.min_obstacle_dist ?? 0).toFixed(2) + 'm';
      obsEl.style.color = 'var(--green-bright)';
    }

    // Sidebar shelf list
    if (cancelled) {
      document.getElementById('shelf-badge').textContent = '0 shelves';
      document.getElementById('shelf-list').innerHTML = `
        <div style="color:var(--amber);font-size:.85rem;text-align:center;padding:16px 0;line-height:1.5;">
          ⛔ Navigation Cancelled.<br>
          <span style="color:var(--text-dim);font-size:.75rem;">Shelves removed from Map. Waiting for next order.</span>
        </div>`;
    } else {
      document.getElementById('shelf-badge').textContent = waypoints.length + ' shelves';
      const listEl = document.getElementById('shelf-list');
      if (!waypoints.length) {
        listEl.innerHTML = `<div style="color:var(--text-dim);font-size:.83rem;text-align:center;padding:16px 0;">
          Send an order from the App to see product locations on the map
        </div>`;
      } else {
        listEl.innerHTML = waypoints.map((wp, idx) => {
          const isActive = idx === activeIdx;
          const isDone   = idx < activeIdx;
          const nPts     = clusterResults[idx] ?? 0;
          const conf     = Math.min(nPts / 12, 1);
          const confPct  = Math.round(conf * 100);
          const items    = wp.items || [];
          const wx = wp.target_x ?? wp.x ?? 0;
          const wy = wp.target_y ?? wp.y ?? 0;
          const statusTxt = isDone ? '✅ REACHED' : (isActive ? '🚀 ACTIVE' : '⏳ QUEUED');
          const cardClass = isDone ? 'shelf-card reached' : (isActive ? 'shelf-card active' : 'shelf-card');
          const nameColor = isActive ? 'var(--red)' : (isDone ? 'var(--green-bright)' : 'var(--text)');
          const barColor  = confPct > 60 ? 'var(--green-bright)' : (confPct > 25 ? 'var(--amber)' : 'var(--text-dim)');
          return `
            <div class="${cardClass}">
              <div class="shelf-header">
                <span class="shelf-name" style="color:${nameColor}">${wp.shelf_id}</span>
                <span class="shelf-status">${statusTxt}</span>
              </div>
              <div class="shelf-coord">📍 (${wx.toFixed(2)}m, ${wy.toFixed(2)}m)</div>
              <div class="product-tags">
                ${items.map(item => `
                  <span class="product-tag ${nPts >= 4 ? 'found' : ''}">
                    ${nPts >= 4 ? '✓' : '🔍'} ${item}
                  </span>
                `).join('')}
              </div>
              <div class="lidar-bar-wrap">
                <div class="lidar-bar-label">
                  <span>LiDAR Confidence</span>
                  <span style="color:${barColor};font-family:monospace">${confPct}%</span>
                </div>
                <div class="lidar-bar">
                  <div class="lidar-bar-fill" style="width:${confPct}%;background:${barColor}"></div>
                </div>
              </div>
            </div>`;
        }).join('');
      }
    }
  }

  async function fetchTelemetry() {
    try {
      const res = await fetch('/api/telemetry');
      if (!res.ok) throw new Error();
      const data = await res.json();

      // Reset cancelled state when active order waypoints arrive
      if (data.waypoints && data.waypoints.length > 0 && data.current_action !== "CANCELLED" && data.order_id !== "CANCELLED") {
        cancelled = false;
        if (data.order_id) lastOrderId = data.order_id;
      }

      // Show/hide cancel button
      if (!cancelled && data.waypoints && data.waypoints.length > 0) {
        document.getElementById('cancel-wrap').style.display = 'block';
      } else {
        document.getElementById('cancel-wrap').style.display = 'none';
      }

      renderScene(data);
    } catch {
      document.getElementById('conn-text').textContent = 'Connecting...';
    }
  }

  setInterval(fetchTelemetry, 100); // 10 Hz
</script>
</body>
</html>
"""

# ==============================================================================
# 2. DEDICATED NAVIGATION COMMANDS & COCKPIT PAGE (Served at '/commands')
# ==============================================================================
COMMANDS_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🧭 CartMate Autonomous Navigation Cockpit</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700;800&family=Outfit:wght@300;400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #070c18;
      --surface: rgba(13,22,42,0.88);
      --surface-bright: rgba(18,30,58,0.95);
      --border: rgba(255,255,255,0.08);
      --cyan: #00f2fe;
      --cyan-glow: rgba(0,242,254,0.35);
      --green: #38ef7d;
      --red: #ff3366;
      --amber: #ffb703;
      --purple: #c084fc;
      --text: #f1f5f9;
      --text-dim: #64748b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Outfit', sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
    }

    header {
      background: rgba(7,12,24,0.98);
      border-bottom: 1px solid var(--border);
      padding: 12px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky; top:0; z-index:100;
      backdrop-filter: blur(16px);
    }
    .brand { display: flex; align-items: center; gap: 14px; }
    .brand-icon {
      width: 42px; height: 42px; border-radius: 12px;
      background: linear-gradient(135deg, #4facfe, #00f2fe);
      display: flex; align-items: center; justify-content: center;
      font-size: 22px;
      box-shadow: 0 0 20px rgba(0,242,254,0.4);
    }
    .brand h1 { font-size: 1.25rem; font-weight: 800; letter-spacing: -0.5px; }
    .brand p { font-size: .74rem; color: var(--text-dim); }

    .nav-actions { display: flex; gap: 12px; align-items: center; }
    .map-btn {
      font-family: 'JetBrains Mono', monospace;
      font-size: .78rem; font-weight: 700;
      padding: 7px 15px; border-radius: 20px;
      text-decoration: none;
      color: var(--cyan);
      background: rgba(0,242,254,0.08);
      border: 1px solid rgba(0,242,254,0.4);
      transition: all .2s;
      display: flex; align-items: center; gap: 6px;
    }
    .map-btn:hover { background: rgba(0,242,254,0.2); box-shadow: 0 0 15px var(--cyan-glow); }

    .pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: .75rem; padding: 6px 14px; border-radius: 20px;
      display: flex; align-items: center; gap: 7px;
      background: rgba(56,239,125,0.08);
      border: 1px solid rgba(56,239,125,0.3);
      color: var(--green);
    }
    .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--green);
      box-shadow: 0 0 10px var(--green); animation: pulse 1.4s infinite; }
    @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.3;transform:scale(.8)} }

    /* --- COCKPIT CONTAINER --- */
    .cockpit {
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 20px;
      max-width: 1400px;
      margin: 0 auto;
      width: 100%;
      flex: 1;
    }

    /* --- HERO COMMAND BANNER --- */
    .hero-command {
      background: var(--surface);
      border: 2px solid var(--cyan);
      border-radius: 20px;
      padding: 24px 32px;
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 24px;
      align-items: center;
      box-shadow: 0 0 35px rgba(0,242,254,0.18);
      transition: all .3s;
      position: relative;
      overflow: hidden;
    }
    .hero-command.stop {
      border-color: var(--red);
      background: rgba(255,51,102,0.08);
      box-shadow: 0 0 35px rgba(255,51,102,0.25);
    }
    .hero-command.reached {
      border-color: var(--green);
      background: rgba(56,239,125,0.08);
      box-shadow: 0 0 35px rgba(56,239,125,0.25);
    }
    .hero-command.cancelled {
      border-color: var(--amber);
      background: rgba(255,183,3,0.08);
      box-shadow: 0 0 35px rgba(255,183,3,0.25);
    }

    .hero-icon-box {
      width: 80px; height: 80px; border-radius: 16px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      display: flex; align-items: center; justify-content: center;
      font-size: 38px;
    }
    .hero-info h2 {
      font-family: 'JetBrains Mono', monospace;
      font-size: 2rem; font-weight: 800; letter-spacing: 1.5px;
      color: var(--cyan);
      text-shadow: 0 0 15px var(--cyan-glow);
    }
    .hero-info p {
      font-size: 1rem; color: var(--text-dim); margin-top: 6px;
    }
    .hero-subtag {
      margin-top: 8px; display: inline-flex; align-items: center; gap: 8px;
      font-family: 'JetBrains Mono', monospace; font-size: .8rem;
      padding: 4px 12px; border-radius: 8px;
      background: rgba(255,255,255,0.05); border: 1px solid var(--border);
    }

    /* Cancel Button on Cockpit */
    .cockpit-cancel-btn {
      padding: 12px 24px;
      background: rgba(255,51,102,0.15);
      border: 1.5px solid var(--red);
      border-radius: 12px;
      color: var(--red);
      font-family: 'JetBrains Mono', monospace;
      font-size: .95rem; font-weight: 700;
      letter-spacing: 1px;
      cursor: pointer;
      transition: all .25s;
    }
    .cockpit-cancel-btn:hover {
      background: rgba(255,51,102,0.3);
      box-shadow: 0 0 22px rgba(255,51,102,0.35);
    }

    /* --- METRICS & COMPASS GRID --- */
    .grid-main {
      display: grid;
      grid-template-columns: 360px 1fr 1fr;
      gap: 20px;
    }
    @media(max-width: 1100px) { .grid-main { grid-template-columns: 1fr; } }

    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
    }
    .card-title {
      font-size: .8rem; text-transform: uppercase; letter-spacing: 1.2px;
      color: var(--text-dim); font-weight: 700; margin-bottom: 16px;
      display: flex; justify-content: space-between; align-items: center;
    }

    /* --- COMPASS / STEERING DIAL --- */
    .compass-wrap {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      padding: 10px 0;
    }
    #compassSvg { width: 220px; height: 220px; }
    .compass-stat {
      margin-top: 12px; text-align: center;
      font-family: 'JetBrains Mono', monospace;
    }
    .compass-stat .val { font-size: 1.4rem; font-weight: 800; color: var(--cyan); }
    .compass-stat .lbl { font-size: .75rem; color: var(--text-dim); margin-top: 2px; }

    /* --- TARGET DESTINATION CARD --- */
    .target-highlight {
      background: rgba(0,242,254,0.05);
      border: 1px solid rgba(0,242,254,0.25);
      border-radius: 14px;
      padding: 16px; margin-bottom: 16px;
    }
    .th-shelf { font-size: 1.3rem; font-weight: 800; color: var(--cyan); display: flex; justify-content: space-between; align-items: center; }
    .th-coord { font-family: 'JetBrains Mono', monospace; font-size: .82rem; color: var(--text-dim); margin-top: 4px; }
    .th-items { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .th-item-tag {
      font-size: .75rem; padding: 3px 10px; border-radius: 99px;
      background: rgba(168,85,247,0.12); border: 1px solid rgba(168,85,247,0.4);
      color: var(--purple); font-weight: 600;
    }

    .dist-meter { margin-top: 14px; }
    .dist-meter-head { display: flex; justify-content: space-between; font-size: .82rem; margin-bottom: 6px; }
    .dist-bar-track { height: 8px; border-radius: 99px; background: rgba(255,255,255,0.08); overflow: hidden; }
    .dist-bar-fill { height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--cyan), var(--green)); transition: width .3s; }

    /* Telemetry Row */
    .tele-row { display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
    .tele-row:last-child { border-bottom: none; }
    .tele-k { font-size: .85rem; color: var(--text-dim); }
    .tele-v { font-family: 'JetBrains Mono', monospace; font-size: .95rem; font-weight: 600; }

    /* --- WAYPOINT SEQUENCE TIMELINE --- */
    .waypoint-steps {
      display: flex; flex-direction: column; gap: 10px; max-height: 290px; overflow-y: auto;
    }
    .wp-step-card {
      display: flex; align-items: center; gap: 14px;
      padding: 12px 14px; border-radius: 12px;
      background: rgba(255,255,255,0.03); border: 1px solid var(--border);
      transition: all .25s;
    }
    .wp-step-card.active {
      border-color: var(--red);
      background: rgba(255,51,102,0.08);
      box-shadow: 0 0 15px rgba(255,51,102,0.2);
    }
    .wp-step-card.done {
      border-color: rgba(56,239,125,0.3);
      background: rgba(56,239,125,0.05);
    }
    .step-num {
      width: 28px; height: 28px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-family: 'JetBrains Mono', monospace; font-size: .8rem; font-weight: 800;
      background: rgba(255,255,255,0.08); color: var(--text);
    }
    .wp-step-card.active .step-num { background: var(--red); color: #fff; }
    .wp-step-card.done .step-num { background: var(--green); color: #000; }
    .step-content { flex: 1; }
    .step-title { font-weight: 700; font-size: .9rem; }
    .step-coord { font-family: 'JetBrains Mono', monospace; font-size: .75rem; color: var(--text-dim); margin-top: 2px; }
    .step-badge {
      font-family: 'JetBrains Mono', monospace; font-size: .7rem; padding: 2px 8px; border-radius: 99px;
      background: rgba(255,255,255,0.08);
    }

    /* --- LIVE COMMAND STREAM LOG --- */
    .terminal-box {
      background: #040811;
      border: 1px solid rgba(0,242,254,0.25);
      border-radius: 16px;
      padding: 18px 20px;
      font-family: 'JetBrains Mono', monospace;
      font-size: .82rem;
      max-height: 250px;
      overflow-y: auto;
      box-shadow: inset 0 0 20px rgba(0,0,0,0.8);
    }
    .terminal-box::-webkit-scrollbar { width: 5px; }
    .terminal-box::-webkit-scrollbar-thumb { background: rgba(0,242,254,0.3); border-radius: 4px; }
    .log-line { padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.03); display: flex; gap: 12px; }
    .log-ts { color: var(--text-dim); }
    .log-cmd { font-weight: 700; color: var(--cyan); }
    .log-cmd.forward { color: var(--green); }
    .log-cmd.turn { color: var(--amber); }
    .log-cmd.stop { color: var(--red); }
    .log-detail { color: var(--text); flex: 1; }
  </style>
</head>
<body>

<header>
  <div class="brand">
    <div class="brand-icon">🧭</div>
    <div>
      <h1>CartMate Autonomous Cockpit</h1>
      <p>Real-Time Adaptive Steering Commands · Live LiDAR Navigation Engine</p>
    </div>
  </div>
  <div class="nav-actions">
    <a href="/" target="_blank" class="map-btn">🗺️ Open 2D LiDAR Map HUD</a>
    <div class="pill"><div class="pulse"></div><span id="conn-state">Connected</span></div>
  </div>
</header>

<div class="cockpit">

  <!-- HERO COMMAND CARD -->
  <div class="hero-command" id="heroCard">
    <div class="hero-icon-box" id="heroIcon">🚀</div>
    <div class="hero-info">
      <h2 id="heroCmd">WAITING FOR APP</h2>
      <p id="heroDesc">Standing by for navigation targets from the mobile order application.</p>
      <div class="hero-subtag" id="heroSubtag">
        <span>📍 Target: <b id="subTarget">None</b></span>
        <span>·</span>
        <span>📏 Distance: <b id="subDist">0.00 m</b></span>
        <span>·</span>
        <span>🔄 Heading Error: <b id="subAngle">0.0°</b></span>
      </div>
    </div>
    <button class="cockpit-cancel-btn" id="cockpitCancelBtn" onclick="cockpitCancel()">⛔ CANCEL MISSION</button>
  </div>

  <!-- MAIN METRICS GRID -->
  <div class="grid-main">

    <!-- 1. COMPASS & HEADING DIAL -->
    <div class="card">
      <div class="card-title">
        <span>🧭 Steering Angle Dial</span>
        <span style="font-family:'JetBrains Mono';font-size:.7rem;color:var(--cyan)" id="dial-mode">±5° Tol</span>
      </div>
      <div class="compass-wrap">
        <svg id="compassSvg" viewBox="0 0 200 200">
          <!-- Outer Dial Ring -->
          <circle cx="100" cy="100" r="90" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="2"/>
          <circle cx="100" cy="100" r="82" fill="none" stroke="rgba(0,242,254,0.15)" stroke-dasharray="3,5" stroke-width="1.5"/>
          <!-- Cardinal Points -->
          <text x="100" y="24" text-anchor="middle" fill="#64748b" font-size="11" font-family="JetBrains Mono">0° (FWD)</text>
          <text x="180" y="104" text-anchor="middle" fill="#64748b" font-size="10" font-family="JetBrains Mono">90°</text>
          <text x="100" y="184" text-anchor="middle" fill="#64748b" font-size="10" font-family="JetBrains Mono">180°</text>
          <text x="22" y="104" text-anchor="middle" fill="#64748b" font-size="10" font-family="JetBrains Mono">-90°</text>
          <!-- Center cross -->
          <line x1="100" y1="35" x2="100" y2="165" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
          <line x1="35" y1="100" x2="165" y2="100" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
          <!-- Needle Group (Rotates with Heading Error) -->
          <g id="needleGroup" transform="rotate(0, 100, 100)">
            <polygon points="100,32 94,100 106,100" fill="#00f2fe" filter="drop-shadow(0 0 6px #00f2fe)"/>
            <polygon points="100,168 95,100 105,100" fill="rgba(255,255,255,0.2)"/>
            <circle cx="100" cy="100" r="8" fill="#070c18" stroke="#00f2fe" stroke-width="3"/>
          </g>
        </svg>
      </div>
      <div class="compass-stat">
        <div class="val" id="dial-angle">0.0°</div>
        <div class="lbl" id="dial-action">STEER STRAIGHT</div>
      </div>
    </div>

    <!-- 2. ACTIVE DESTINATION & TELEMETRY -->
    <div class="card">
      <div class="card-title">
        <span>🎯 Active Target Shelf</span>
        <span class="step-badge" id="step-badge">WAITING</span>
      </div>
      <div class="target-highlight">
        <div class="th-shelf">
          <span id="targetName">No Active Goal</span>
          <span style="font-size:.85rem;color:var(--green);" id="targetDistM">0.00 m</span>
        </div>
        <div class="th-coord" id="targetCoords">X: 0.00 m | Y: 0.00 m</div>
        <div class="th-items" id="targetItems">
          <span class="th-item-tag">No Items</span>
        </div>
        <div class="dist-meter">
          <div class="dist-meter-head">
            <span style="color:var(--text-dim)">Distance to Goal</span>
            <span id="distPct" style="font-family:'JetBrains Mono';font-weight:700">0%</span>
          </div>
          <div class="dist-bar-track">
            <div class="dist-bar-fill" id="distBar" style="width:0%"></div>
          </div>
        </div>
      </div>

      <div class="tele-row">
        <span class="tele-k">Cart Position (Odometry)</span>
        <span class="tele-v" id="cartCoords">X: 0.00m, Y: 0.00m</span>
      </div>
      <div class="tele-row">
        <span class="tele-k">Cart Heading Angle</span>
        <span class="tele-v" id="cartHeading">0.0°</span>
      </div>
      <div class="tele-row">
        <span class="tele-k">Front LiDAR Clearance</span>
        <span class="tele-v" id="cartClearance" style="color:var(--green)">Clear</span>
      </div>
    </div>

    <!-- 3. MISSION WAYPOINT SEQUENCE -->
    <div class="card">
      <div class="card-title">
        <span>📋 Mission Route Sequence</span>
        <span style="font-family:'JetBrains Mono';font-size:.75rem" id="missionCount">0 steps</span>
      </div>
      <div class="waypoint-steps" id="waypointSteps">
        <div style="color:var(--text-dim);font-size:.84rem;text-align:center;padding:24px 0;">
          No active mission loaded. Send an order from the mobile app.
        </div>
      </div>
    </div>

  </div>

  <!-- LIVE DECISION & COMMAND STREAM LOG -->
  <div class="card" style="margin-top:4px;">
    <div class="card-title">
      <span>⚡ Real-Time PathPlanner Decision Stream</span>
      <span style="font-family:'JetBrains Mono';font-size:.7rem;color:var(--text-dim)">10 Hz Loop Frequency</span>
    </div>
    <div class="terminal-box" id="terminalLog">
      <div class="log-line">
        <span class="log-ts">[BOOT]</span>
        <span class="log-cmd">INITIALIZED</span>
        <span class="log-detail">CartMate Navigation Engine online. Listening for mission targets...</span>
      </div>
    </div>
  </div>

</div>

<script>
  let lastAction = '';
  let maxInitialDist = 3.0;
  let logHistory = [];

  function appendLog(cmd, detail) {
    const timeStr = new Date().toTimeString().split(' ')[0];
    let cmdClass = 'forward';
    if (cmd.includes('TURN')) cmdClass = 'turn';
    else if (cmd.includes('STOP') || cmd.includes('CANCEL')) cmdClass = 'stop';

    const box = document.getElementById('terminalLog');
    const line = document.createElement('div');
    line.className = 'log-line';
    line.innerHTML = `
      <span class="log-ts">[${timeStr}]</span>
      <span class="log-cmd ${cmdClass}">${cmd}</span>
      <span class="log-detail">${detail}</span>
    `;
    box.appendChild(line);
    while (box.children.length > 50) box.removeChild(box.firstChild);
    box.scrollTop = box.scrollHeight;
  }

  async function cockpitCancel() {
    try {
      await fetch('/api/cancel', { method: 'POST' });
    } catch(e) {}
    appendLog('CANCELLED', 'User requested mission termination via Cockpit button. Motors halted.');
    updateHero('CANCELLED', 0, 0, false, null);
  }

  function updateHero(action, dist, angleErr, isBlocked, activeWp) {
    const card = document.getElementById('heroCard');
    const icon = document.getElementById('heroIcon');
    const cmd  = document.getElementById('heroCmd');
    const desc = document.getElementById('heroDesc');

    card.className = 'hero-command';

    if (action === 'CANCELLED') {
      card.classList.add('cancelled');
      icon.textContent = '⛔';
      cmd.textContent  = 'NAVIGATION CANCELLED';
      cmd.style.color  = 'var(--amber)';
      desc.textContent = 'Mission was cancelled by operator. Shelves cleared, cart stopped.';
      return;
    }

    if (action === 'REACHED' || action.startsWith('CAMERA') || action.startsWith('ROBOTIC')) {
      card.classList.add('reached');
      icon.textContent = '✓';
      cmd.textContent  = action === 'REACHED' ? 'GOAL REACHED (SHELF)' : action;
      cmd.style.color  = 'var(--green)';
      desc.textContent = activeWp ? `Successfully arrived at ${activeWp.shelf_id}! Target shelf confirmed.` : 'Goal reached.';
      return;
    }

    if (action === 'ALL_GOALS_REACHED') {
      card.classList.add('reached');
      icon.textContent = '🏁';
      cmd.textContent  = 'ALL GOALS COMPLETED';
      cmd.style.color  = 'var(--green)';
      desc.textContent = 'All waypoints in the current mission order have been completed successfully.';
      return;
    }

    if (action === 'EMERGENCY_STOP' || (isBlocked && action !== 'MOVE_BACKWARD' && action !== 'TURN_LEFT' && action !== 'TURN_RIGHT')) {
      card.classList.add('stop');
      icon.textContent = '🚨';
      cmd.textContent  = 'EMERGENCY STOP (OBSTACLE)';
      cmd.style.color  = 'var(--red)';
      desc.textContent = 'Front LiDAR detected obstacle in forward path! Halting cart safely.';
      return;
    }

    if (action === 'MOVE_BACKWARD') {
      icon.textContent = '▼';
      cmd.textContent  = 'REVERSING (CLEAR OBSTACLE)';
      cmd.style.color  = 'var(--amber)';
      desc.textContent = 'Obstacle recovery active: Reversing to gain safe clearance before steering.';
    } else if (action === 'MOVE_FORWARD') {
      icon.textContent = '▲';
      cmd.textContent  = 'MOVE FORWARD';
      cmd.style.color  = 'var(--green)';
      desc.textContent = `Heading aligned within tolerance (Error: ${angleErr.toFixed(1)}°). Cruising forward towards shelf.`;
    } else if (action === 'TURN_LEFT') {
      icon.textContent = '↺';
      cmd.textContent  = 'TURN LEFT';
      cmd.style.color  = 'var(--amber)';
      desc.textContent = `Steering left towards target (Heading error: ${angleErr.toFixed(1)}°).`;
    } else if (action === 'TURN_RIGHT') {
      icon.textContent = '↻';
      cmd.textContent  = 'TURN RIGHT';
      cmd.style.color  = 'var(--amber)';
      desc.textContent = `Steering right towards target (Heading error: ${angleErr.toFixed(1)}°).`;
    } else {
      icon.textContent = '⏳';
      cmd.textContent  = action || 'STANDBY';
      cmd.style.color  = 'var(--cyan)';
      desc.textContent = 'Waiting for coordinates and route calculation from mobile app.';
    }
  }

  function updateCompass(angleErr) {
    const needle = document.getElementById('needleGroup');
    needle.setAttribute('transform', `rotate(${angleErr}, 100, 100)`);
    document.getElementById('dial-angle').textContent = `${angleErr > 0 ? '+' : ''}${angleErr.toFixed(1)}°`;

    const actEl = document.getElementById('dial-action');
    if (Math.abs(angleErr) <= 5.0) {
      actEl.textContent = 'STEER STRAIGHT ▲';
      actEl.style.color = 'var(--green)';
    } else if (angleErr > 0) {
      actEl.textContent = 'STEER LEFT ↺';
      actEl.style.color = 'var(--amber)';
    } else {
      actEl.textContent = 'STEER RIGHT ↻';
      actEl.style.color = 'var(--amber)';
    }
  }

  async function fetchCockpitTelemetry() {
    try {
      const res = await fetch('/api/telemetry');
      if (!res.ok) throw new Error();
      const data = await res.json();

      const waypoints = data.waypoints || [];
      const activeIdx = data.active_waypoint_index ?? 0;
      const action    = data.current_action || 'IDLE';
      const dist      = data.distance_to_target ?? 0.0;
      const angleErr  = data.angle_error ?? 0.0;
      const isBlocked = data.is_blocked || false;
      const pose      = data.cart_pose || { x:0, y:0, theta:0 };

      const activeWp  = (waypoints.length > activeIdx) ? waypoints[activeIdx] : null;

      // Log decision change
      if (action !== lastAction && action !== 'IDLE') {
        const detail = activeWp ? `Target: ${activeWp.shelf_id} (Dist: ${dist.toFixed(2)}m, Err: ${angleErr.toFixed(1)}°)` : `Dist: ${dist.toFixed(2)}m`;
        appendLog(action, detail);
        lastAction = action;
      }

      // Hero banner
      updateHero(action, dist, angleErr, isBlocked, activeWp);

      // Subtag info
      document.getElementById('subTarget').textContent = activeWp ? activeWp.shelf_id : 'None';
      document.getElementById('subDist').textContent   = dist.toFixed(2) + ' m';
      document.getElementById('subAngle').textContent  = angleErr.toFixed(1) + '°';

      // Compass dial
      updateCompass(angleErr);

      // Target Card
      if (activeWp) {
        document.getElementById('step-badge').textContent = `STEP ${activeIdx+1}/${waypoints.length}`;
        document.getElementById('targetName').textContent = activeWp.shelf_id || 'Shelf';
        document.getElementById('targetDistM').textContent = dist.toFixed(2) + ' m';
        const wx = activeWp.target_x ?? activeWp.x ?? 0;
        const wy = activeWp.target_y ?? activeWp.y ?? 0;
        document.getElementById('targetCoords').textContent = `Coordinates -> X: ${wx.toFixed(2)} m | Y: ${wy.toFixed(2)} m`;

        const items = activeWp.items || [];
        document.getElementById('targetItems').innerHTML = items.length
          ? items.map(it => `<span class="th-item-tag">🛍️ ${it}</span>`).join('')
          : '<span class="th-item-tag">No Specific Items</span>';

        // Progress calculation
        if (dist > maxInitialDist) maxInitialDist = dist;
        const pct = Math.max(0, Math.min(100, Math.round((1 - dist / maxInitialDist) * 100)));
        document.getElementById('distPct').textContent = pct + '%';
        document.getElementById('distBar').style.width = pct + '%';
      } else {
        document.getElementById('step-badge').textContent = action === 'CANCELLED' ? 'CANCELLED' : 'IDLE';
        document.getElementById('targetName').textContent = action === 'CANCELLED' ? 'Mission Cancelled' : 'No Active Goal';
        document.getElementById('targetDistM').textContent = '0.00 m';
        document.getElementById('targetCoords').textContent = 'Coordinates -> X: – | Y: –';
        document.getElementById('targetItems').innerHTML = '<span class="th-item-tag">None</span>';
        document.getElementById('distPct').textContent = '0%';
        document.getElementById('distBar').style.width = '0%';
      }

      // Odometry
      document.getElementById('cartCoords').textContent  = `X: ${pose.x.toFixed(2)}m, Y: ${pose.y.toFixed(2)}m`;
      document.getElementById('cartHeading').textContent = `${pose.theta.toFixed(1)}°`;

      // Clearance
      const clrEl = document.getElementById('cartClearance');
      if (isBlocked) {
        clrEl.textContent = `BLOCKED ${(data.min_obstacle_dist ?? 0).toFixed(2)}m`;
        clrEl.style.color = 'var(--red)';
      } else {
        clrEl.textContent = `Clear ${(data.min_obstacle_dist ?? 0).toFixed(2)}m`;
        clrEl.style.color = 'var(--green)';
      }

      // Mission timeline
      document.getElementById('missionCount').textContent = waypoints.length + ' steps';
      const stepsBox = document.getElementById('waypointSteps');
      if (!waypoints.length) {
        stepsBox.innerHTML = `
          <div style="color:var(--text-dim);font-size:.84rem;text-align:center;padding:24px 0;">
            ${action === 'CANCELLED' ? '⛔ Mission was cancelled. Shelves cleared.' : 'No active mission. Send an order from the app.'}
          </div>`;
      } else {
        stepsBox.innerHTML = waypoints.map((wp, i) => {
          const isAct = (i === activeIdx);
          const isDn  = (i < activeIdx);
          const wx = wp.target_x ?? wp.x ?? 0;
          const wy = wp.target_y ?? wp.y ?? 0;
          const cardCls = isDn ? 'wp-step-card done' : (isAct ? 'wp-step-card active' : 'wp-step-card');
          const badgeTxt = isDn ? 'DONE ✓' : (isAct ? 'ACTIVE 🚀' : 'QUEUED ⏳');
          return `
            <div class="${cardCls}">
              <div class="step-num">${i+1}</div>
              <div class="step-content">
                <div class="step-title">${wp.shelf_id || 'Shelf'}</div>
                <div class="step-coord">(${wx.toFixed(2)}m, ${wy.toFixed(2)}m) · ${(wp.items || []).join(', ')}</div>
              </div>
              <div class="step-badge">${badgeTxt}</div>
            </div>`;
        }).join('');
      }

    } catch(e) {
      document.getElementById('conn-state').textContent = 'Connecting...';
    }
  }

  setInterval(fetchCockpitTelemetry, 100); // 10 Hz
</script>
</body>
</html>
"""

# ==============================================================================
# 3. GLOBAL TELEMETRY STORE & HTTP SERVER
# ==============================================================================
_navigation_cancelled = False
_cancel_lock = threading.Lock()

def is_navigation_cancelled():
    """Returns True if user cancelled navigation from either browser window."""
    with _cancel_lock:
        return _navigation_cancelled

def reset_navigation_cancel():
    """Reset cancel flag when a new order arrives."""
    global _navigation_cancelled
    with _cancel_lock:
        _navigation_cancelled = False


class TelemetryDataStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = {
            "order_id": "ORD_0001",
            "cart_id": "CART_01",
            "cart_pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
            "lidar_points": [],
            "waypoints": [],
            "active_waypoint_index": 0,
            "current_action": "IDLE",
            "distance_to_target": 0.0,
            "angle_error": 0.0,
            "is_blocked": False,
            "min_obstacle_dist": 0.0,
            "timestamp": time.time()
        }

    def update(self, **kwargs):
        with self.lock:
            self.data.update(kwargs)
            self.data["timestamp"] = time.time()

    def cancel_navigation(self):
        """Immediately clear waypoints and mark status as CANCELLED"""
        with self.lock:
            self.data["waypoints"] = []
            self.data["current_action"] = "CANCELLED"
            self.data["distance_to_target"] = 0.0
            self.data["angle_error"] = 0.0
            self.data["order_id"] = "CANCELLED"
            self.data["timestamp"] = time.time()

    def get_json(self):
        with self.lock:
            return json.dumps(self.data)

telemetry_store = TelemetryDataStore()


class CustomHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # 1. Main 2D LiDAR Map HUD
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        # 2. Dedicated Navigation Commands & Cockpit Page
        elif self.path in ("/commands", "/commands.html", "/navigation", "/navigation.html", "/cockpit"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(COMMANDS_HTML_TEMPLATE.encode("utf-8"))

        # 3. Telemetry JSON API
        elif self.path == "/api/telemetry":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(telemetry_store.get_json().encode("utf-8"))

        # 4. Hi-Res Map PNG
        elif self.path == "/map.png":
            map_path = os.path.join(os.getcwd(), "map.png")
            if os.path.exists(map_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with open(map_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global _navigation_cancelled
        if self.path == "/api/cancel":
            with _cancel_lock:
                _navigation_cancelled = True
            telemetry_store.cancel_navigation()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status":"cancelled"}')
            print("⛔ [Web HUD] Navigation cancelled by user via browser button. Waypoints cleared.")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress console clutter


class WebVisualizer:
    def __init__(self, host="0.0.0.0", port=8080):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        try:
            socketserver.TCPServer.allow_reuse_address = True
            self.server = socketserver.TCPServer((self.host, self.port), CustomHTTPHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"🌐 [Web HUD] Live at http://10.104.67.204:{self.port}")
            print(f"🧭 [Navigation Cockpit] Live at http://10.104.67.204:{self.port}/commands")
            return True
        except Exception as e:
            print(f"⚠️ [Web HUD] Failed to start: {e}")
            return False

    def update_telemetry(self, **kwargs):
        telemetry_store.update(**kwargs)

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print("🌐 [Web HUD] Stopped.")

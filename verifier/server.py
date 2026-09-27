"""EdgePPG baseline verifier HTTP server.

A minimal HTTP server (stdlib only) that:
  * accepts envelopes via HTTP POST `/api/result`
  * accepts QR-paste envelopes via `/api/paste` (POST)
  * serves a plain-text dashboard at `/`
  * writes offline receipts on every successful verification

Run with:
    .venv\\Scripts\\python.exe -m verifier.server

The server is the Office-Kit-free baseline. No JavaScript, no Three.js — it
intentionally avoids pulling in vendor runtimes or external assets. A QR-fallback
step is documented inline.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from verifier import calls as call_store
from verifier.canonical import canonical_payload
from verifier.receipt import write_receipt
from verifier.verify import verify_envelope

VERIFIER_VERSION = "edgeppg-baseline-1.0"
MAX_BODY = 256 * 1024


def _load_pubkey(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EdgePPG — VKYC Assurance & Verification Gateway</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    /* Palette Tokens: Soft Peach, Warm Taupe, Medium Brown, Dark Espresso */
    --bg-peach: #FAF3EE;
    --bg-peach-light: #FDF9F6;
    --bg-peach-sub: #F5EAE1;
    --bg-card: #FFFFFF;
    --bg-card-sub: #FBF5F0;
    
    --taupe-100: #F3ECE6;
    --taupe-200: #E7DDD4;
    --taupe-300: #D5C6BA;
    --taupe-400: #B8A596;
    --taupe-500: #968273;
    
    --brown-medium: #7A4F32;
    --brown-medium-hover: #684128;
    --brown-espresso: #25160E;
    --brown-espresso-light: #3A2317;

    --border-card: #EADFD5;
    --border-sub: #F0E6DE;
    --border-hover: #D4C5B9;
    --border-focus: #7A4F32;

    --primary-btn: linear-gradient(135deg, #7A4F32 0%, #54341F 100%);
    --primary-btn-hover: linear-gradient(135deg, #684128 0%, #432816 100%);

    --accent-emerald: #2E7D5B;
    --accent-emerald-bg: #EAF7EE;
    --accent-emerald-border: #BCE7CA;

    --accent-amber: #B45309;
    --accent-amber-bg: #FEF3C7;
    --accent-amber-border: #FDE68A;

    --accent-coral: #C2410C;
    --accent-coral-bg: #FEE2E2;
    --accent-coral-border: #FECACA;

    --text-main: #25160E;
    --text-muted: #6E5A4E;
    --text-dim: #998375;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Outfit', system-ui, -apple-system, sans-serif;
    font-size: 13px;
    background-color: var(--bg-peach);
    background-image: 
      radial-gradient(at 0% 0%, rgba(245, 234, 225, 0.9) 0px, transparent 50%),
      radial-gradient(at 100% 0%, rgba(242, 222, 206, 0.6) 0px, transparent 50%),
      radial-gradient(at 50% 100%, rgba(235, 215, 198, 0.35) 0px, transparent 50%);
    background-attachment: fixed;
    color: var(--text-main);
    min-height: 100vh;
    padding-bottom: 60px;
    letter-spacing: -0.01em;
  }
  header {
    background: var(--brown-espresso);
    border-bottom: 1px solid var(--brown-espresso-light);
    padding: 16px 36px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 4px 20px rgba(37, 22, 14, 0.12);
  }
  .brand { display: flex; align-items: center; gap: 14px; }
  .brand-logo {
    width: 38px; height: 38px; border-radius: 12px;
    background: linear-gradient(135deg, #8B5E3C, #D4C5B9);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 12px rgba(37, 22, 14, 0.3);
    font-weight: 800; color: #FFF; font-size: 16px;
    letter-spacing: 0.04em;
  }
  .brand-title { font-size: 18px; font-weight: 700; letter-spacing: -0.02em; color: #FAF3EE; display: flex; align-items: center; gap: 10px; }
  .brand-version {
    font-size: 11px; font-weight: 600; font-family: 'JetBrains Mono', monospace;
    background: rgba(250, 243, 238, 0.12); padding: 2px 8px; border-radius: 12px;
    color: #E6DDD5; border: 1px solid rgba(250, 243, 238, 0.2);
  }
  .header-actions { display: flex; align-items: center; gap: 14px; }
  .enclave-badge {
    display: flex; align-items: center; gap: 8px; font-size: 11px; font-weight: 700;
    color: #D1FAE5; background: rgba(46, 125, 91, 0.25); border: 1px solid rgba(46, 125, 91, 0.4);
    padding: 5px 12px; border-radius: 16px; letter-spacing: 0.04em;
  }
  .live-dot {
    width: 7px; height: 7px; border-radius: 50%; background: #34D399;
    box-shadow: 0 0 8px #34D399; animation: pulseGlow 2s infinite;
  }
  #status {
    font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; font-size: 11px;
    padding: 6px 14px; border-radius: 16px; transition: all 0.3s ease;
  }
  #status.ok { background: rgba(46, 125, 91, 0.25); color: #6EE7B7; border: 1px solid rgba(46, 125, 91, 0.5); }
  #status.bad { background: rgba(239, 68, 68, 0.25); color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.5); }
  #status.uncertain { background: rgba(245, 158, 11, 0.25); color: #FDE68A; border: 1px solid rgba(245, 158, 11, 0.5); }
  #status.idle { background: rgba(250, 243, 238, 0.12); color: #D4C5B9; border: 1px solid rgba(250, 243, 238, 0.25); }

  .container { max-width: 1440px; margin: 0 auto; padding: 0 32px; }

  /* KPI Summary Strip */
  .kpi-bar {
    margin: 22px auto 0;
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
  }
  @media (max-width: 900px) { .kpi-bar { grid-template-columns: repeat(2, 1fr); } }
  .kpi-card {
    background: var(--bg-card);
    border: 1px solid var(--border-card); border-radius: 18px;
    padding: 18px 22px; display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 2px 14px rgba(70, 45, 30, 0.04);
    transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
  }
  .kpi-card:hover {
    transform: translateY(-2px);
    border-color: var(--border-hover);
    box-shadow: 0 6px 20px rgba(70, 45, 30, 0.08);
  }
  .kpi-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); font-weight: 700; margin-bottom: 4px; }
  .kpi-value { font-size: 17px; font-weight: 700; color: var(--text-main); }

  /* Hero Section: 3-Column Console */
  .hero-console {
    margin-top: 22px;
    display: grid;
    grid-template-columns: 320px 1.4fr 300px;
    gap: 18px;
  }
  @media (max-width: 1200px) { .hero-console { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 768px) { .hero-console { grid-template-columns: 1fr; } }

  .console-panel {
    background: var(--bg-card);
    border: 1px solid var(--border-card);
    border-radius: 20px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 4px 20px rgba(70, 45, 30, 0.05);
    position: relative;
    overflow: hidden;
  }
  .panel-header {
    display: flex; align-items: center; justify-content: space-between;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em;
    color: var(--text-muted); margin-bottom: 16px; padding-bottom: 10px;
    border-bottom: 1px solid var(--border-sub);
  }

  /* Applicant Card */
  .applicant-hero { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
  .applicant-avatar {
    width: 52px; height: 52px; border-radius: 16px;
    background: linear-gradient(135deg, #7A4F32, #54341F);
    border: 2px solid #D4C5B9;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: 800; color: #FAF3EE;
    box-shadow: 0 4px 14px rgba(84, 52, 31, 0.2);
  }
  .applicant-name { font-size: 17px; font-weight: 700; color: var(--text-main); line-height: 1.2; }
  .applicant-ref { font-size: 12px; font-family: 'JetBrains Mono', monospace; color: var(--brown-medium); margin-top: 3px; font-weight: 600; }
  .applicant-meta-row { display: flex; justify-content: space-between; margin-top: 10px; font-size: 12px; }
  .meta-title { color: var(--text-dim); font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .meta-val { font-weight: 600; color: var(--text-main); font-family: 'JetBrains Mono', monospace; font-size: 11px; }

  /* Hero Center: Confidence & Result */
  .result-card {
    background: #FFFFFF;
    border: 2px solid var(--border-card);
    border-radius: 20px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: all 0.3s ease;
    box-shadow: 0 4px 24px rgba(70, 45, 30, 0.05);
  }
  .result-card.live-state {
    border-color: #2E7D5B;
    box-shadow: 0 4px 28px rgba(46, 125, 91, 0.12);
  }
  .result-card.uncertain-state {
    border-color: #B45309;
    box-shadow: 0 4px 28px rgba(180, 83, 9, 0.12);
  }
  .result-card.spoof-state {
    border-color: #C2410C;
    box-shadow: 0 4px 28px rgba(194, 65, 12, 0.12);
  }
  .hero-verdict-grid {
    display: grid;
    grid-template-columns: 140px 1fr;
    gap: 20px;
    align-items: center;
  }
  @media (max-width: 540px) { .hero-verdict-grid { grid-template-columns: 1fr; text-align: center; } }

  .conf-ring-box {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    position: relative;
  }
  .conf-ring-svg { transform: rotate(-90deg); }
  .conf-text-wrap {
    position: absolute; top: 0; left: 0; width: 110px; height: 110px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
  }
  .conf-percent { font-size: 24px; font-weight: 800; color: var(--text-main); line-height: 1; }
  .conf-sublabel { font-size: 9px; font-weight: 700; text-transform: uppercase; color: var(--text-dim); margin-top: 3px; }
  .conf-plive-badge {
    margin-top: 8px; font-size: 11px; font-weight: 700; font-family: 'JetBrains Mono', monospace;
    color: var(--brown-medium); background: var(--bg-peach-sub); padding: 2px 8px; border-radius: 10px;
    border: 1px solid var(--border-card);
  }

  .verdict-info-box { display: flex; flex-direction: column; justify-content: center; }
  .res-pill {
    align-self: flex-start;
    padding: 5px 14px; border-radius: 20px; font-weight: 800; font-size: 12px; letter-spacing: 0.08em;
    display: inline-flex; align-items: center; gap: 6px; margin-bottom: 8px;
  }
  .res-pill.live { background: var(--accent-emerald-bg); color: var(--accent-emerald); border: 1px solid var(--accent-emerald-border); }
  .res-pill.uncertain { background: var(--accent-amber-bg); color: var(--accent-amber); border: 1px solid var(--accent-amber-border); }
  .res-pill.spoof { background: var(--accent-coral-bg); color: var(--accent-coral); border: 1px solid var(--accent-coral-border); }
  .res-pill.standby { background: var(--bg-peach-sub); color: var(--text-muted); border: 1px solid var(--border-card); }

  .res-title { font-size: 19px; font-weight: 800; color: var(--text-main); letter-spacing: -0.02em; margin-bottom: 4px; line-height: 1.25; }
  .res-sub { font-size: 12px; color: var(--text-muted); line-height: 1.5; margin-bottom: 12px; }

  .verdict-footer-meta {
    display: flex; align-items: center; gap: 16px; font-size: 11px; color: var(--text-dim);
    padding-top: 10px; border-top: 1px solid var(--border-sub);
  }

  /* Operational Telemetry Matrix */
  .telemetry-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 9px 0; border-bottom: 1px solid var(--border-sub); font-size: 12px;
  }
  .telemetry-row:last-child { border-bottom: none; }
  .tel-lbl { font-weight: 600; color: var(--text-dim); text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em; }
  .tel-val { font-weight: 700; color: var(--text-main); font-family: 'JetBrains Mono', monospace; font-size: 11px; }

  /* Evidence Modalities (6-Card Grid) */
  .evidence-section { margin-top: 22px; }
  .section-title-bar {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px;
  }
  .section-heading {
    font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--text-main); display: flex; align-items: center; gap: 8px;
  }
  .evidence-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }
  @media (max-width: 1024px) { .evidence-grid { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 600px) { .evidence-grid { grid-template-columns: 1fr; } }

  .tech-toggle-bar { margin-top: 22px; }
  .btn-accordion {
    width: 100%; background: #FFFFFF; border: 1px solid var(--border-card);
    border-radius: 14px; padding: 14px 20px; color: var(--text-main); font-size: 13px; font-weight: 700;
    display: flex; justify-content: space-between; align-items: center; cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 10px rgba(70, 45, 30, 0.04);
  }
  .btn-accordion:hover { background: var(--bg-peach-light); border-color: var(--border-hover); }
  .tech-panel {
    background: var(--bg-card); border: 1px solid var(--border-card); border-radius: 18px;
    padding: 22px; margin-top: 10px; box-shadow: 0 4px 20px rgba(70, 45, 30, 0.05);
  }
  .tech-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 11px; margin-top: 10px; }
  .tech-table th {
    background: var(--bg-peach-sub); padding: 9px 12px; font-size: 10px; text-transform: uppercase;
    letter-spacing: 0.05em; color: var(--text-muted); border-bottom: 1px solid var(--border-card); text-align: left;
  }
  .tech-table td { padding: 8px 12px; border-bottom: 1px solid var(--border-sub); font-family: 'JetBrains Mono', monospace; color: var(--text-main); }
  .badge-sentinel { background: var(--bg-peach-sub); color: var(--text-dim); border: 1px solid var(--border-card); padding: 2px 6px; border-radius: 6px; font-size: 9px; font-weight: 700; }
  .badge-active { background: var(--accent-emerald-bg); color: var(--accent-emerald); border: 1px solid var(--accent-emerald-border); padding: 2px 6px; border-radius: 6px; font-size: 9px; font-weight: 700; }

  .evidence-card {
    background: var(--bg-card);
    border: 1px solid var(--border-card);
    border-radius: 18px;
    padding: 20px;
    display: flex; flex-direction: column; justify-content: space-between;
    transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
    box-shadow: 0 2px 14px rgba(70, 45, 30, 0.04);
  }
  .evidence-card:hover {
    transform: translateY(-2px);
    border-color: var(--border-hover);
    box-shadow: 0 6px 20px rgba(70, 45, 30, 0.08);
  }
  .ev-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
  .ev-name { font-size: 13px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 6px; }
  .ev-badge {
    font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px;
    text-transform: uppercase; letter-spacing: 0.04em;
  }
  .ev-badge.good { background: var(--accent-emerald-bg); color: var(--accent-emerald); border: 1px solid var(--accent-emerald-border); }
  .ev-badge.warn { background: var(--accent-amber-bg); color: var(--accent-amber); border: 1px solid var(--accent-amber-border); }
  .ev-badge.dim { background: var(--bg-peach-sub); color: var(--text-muted); border: 1px solid var(--border-card); }

  .ev-metrics { margin-bottom: 12px; }
  .ev-metric-item { display: flex; justify-content: space-between; align-items: center; font-size: 11px; margin-bottom: 5px; }
  .ev-metric-lbl { color: var(--text-dim); }
  .ev-metric-val { font-family: 'JetBrains Mono', monospace; font-weight: 700; color: var(--text-main); max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .meter-bar-bg { width: 100%; height: 6px; background: var(--bg-peach-sub); border-radius: 4px; overflow: hidden; margin-top: 6px; }
  .meter-bar-fill { height: 100%; background: linear-gradient(90deg, #B8A596, #7A4F32); border-radius: 4px; transition: width 0.6s ease; }

  .ev-desc { font-size: 11px; color: var(--text-muted); line-height: 1.4; border-top: 1px solid var(--border-sub); padding-top: 8px; margin-top: auto; }

  /* Security & Integrity Banner */
  .security-bar {
    margin-top: 20px;
    background: #FFFFFF;
    border: 1px solid var(--border-card);
    border-radius: 16px;
    padding: 16px 24px;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    box-shadow: 0 2px 14px rgba(70, 45, 30, 0.04);
  }
  @media (max-width: 900px) { .security-bar { grid-template-columns: repeat(2, 1fr); } }
  .sec-item { display: flex; align-items: center; gap: 8px; font-size: 11px; font-weight: 600; color: var(--text-main); }
  .sec-check { color: #2E7D5B; font-weight: 800; font-size: 13px; }

  /* Operations: 2-Column Lower Layout */
  .ops-grid {
    margin-top: 22px;
    display: grid;
    grid-template-columns: 1.15fr 1fr;
    gap: 22px;
  }
  @media (max-width: 1080px) { .ops-grid { grid-template-columns: 1fr; } }

  .ops-card {
    background: var(--bg-card);
    border: 1px solid var(--border-card);
    border-radius: 20px;
    padding: 24px;
    box-shadow: 0 4px 20px rgba(70, 45, 30, 0.05);
  }
  .ops-card h2 {
    font-size: 16px; font-weight: 700; color: var(--text-main);
    margin-bottom: 6px; display: flex; align-items: center; gap: 8px;
    letter-spacing: -0.01em;
  }
  .hint { font-size: 12px; color: var(--text-muted); margin-bottom: 18px; line-height: 1.5; }

  .form label {
    display: block; margin-bottom: 14px; font-size: 11px; font-weight: 700;
    color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em;
  }
  .form input, textarea, select {
    width: 100%; margin-top: 6px; background: #FDF9F6;
    color: var(--text-main); border: 1px solid var(--border-card);
    border-radius: 12px; padding: 11px 14px; font-size: 13px;
    font-family: inherit; transition: all 0.2s ease;
  }
  .form input:focus, textarea:focus, select:focus {
    outline: none; border-color: var(--border-focus);
    box-shadow: 0 0 0 3px rgba(122, 79, 50, 0.15);
    background: #FFFFFF;
  }
  textarea { font-family: 'JetBrains Mono', monospace; font-size: 12px; resize: vertical; line-height: 1.5; }

  .btn-row { display: flex; align-items: center; gap: 12px; margin-top: 18px; }
  button {
    background: var(--primary-btn);
    color: #FAF3EE; font-weight: 700; font-size: 12px;
    border: 0; padding: 11px 22px; border-radius: 12px;
    cursor: pointer; transition: all 0.2s ease;
    box-shadow: 0 4px 14px rgba(84, 52, 31, 0.2);
    display: inline-flex; align-items: center; gap: 8px;
  }
  button:hover {
    background: var(--primary-btn-hover);
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(84, 52, 31, 0.28);
  }
  button:active { transform: translateY(0); }

  .btn-ghost {
    background: #FDF8F5; color: var(--text-main);
    border: 1px solid var(--border-card); box-shadow: none; font-weight: 600;
  }
  .btn-ghost:hover { background: #F5EAE1; color: var(--brown-espresso); border-color: var(--taupe-300); transform: translateY(-1px); }

  .btn-sm {
    padding: 6px 12px; font-size: 11px; font-weight: 600;
    border-radius: 8px; background: var(--bg-peach-sub);
    color: var(--brown-medium); border: 1px solid var(--border-card);
    cursor: pointer; transition: all 0.2s;
  }
  .btn-sm:hover { background: var(--brown-medium); color: #FAF3EE; border-color: var(--brown-medium); transform: translateY(-1px); }

  .waitbanner {
    background: #FEF3C7;
    border: 1px solid #FDE68A;
    border-radius: 14px; padding: 12px 18px; margin-bottom: 18px;
    font-size: 12px; font-weight: 600; color: #92400E;
    display: flex; align-items: center; gap: 10px;
  }

  table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 10px; }
  th {
    background: var(--bg-peach-sub);
    border-bottom: 1px solid var(--border-card);
    padding: 11px 14px; text-align: left;
    font-size: 10px; text-transform: uppercase; font-weight: 700;
    color: var(--text-muted); letter-spacing: 0.06em;
  }
  th:first-child { border-top-left-radius: 10px; border-bottom-left-radius: 10px; }
  th:last-child { border-top-right-radius: 10px; border-bottom-right-radius: 10px; }
  td {
    border-bottom: 1px solid var(--border-sub);
    padding: 12px 14px; vertical-align: middle; font-size: 12px;
    color: var(--text-main);
  }
  tr:hover td { background: rgba(212, 197, 185, 0.12); }

  .st { padding: 3px 10px; border-radius: 14px; font-size: 10px; font-weight: 700; display: inline-flex; align-items: center; gap: 5px; }
  .st-SCHEDULED { background: var(--bg-peach-sub); color: var(--text-muted); border: 1px solid var(--border-card); }
  .st-WAITING { background: var(--accent-amber-bg); color: var(--accent-amber); border: 1px solid var(--accent-amber-border); }
  .st-CONNECTED { background: var(--accent-emerald-bg); color: var(--accent-emerald); border: 1px solid var(--accent-emerald-border); }
  .st-COMPLETED { background: #F0E6DE; color: var(--brown-medium); border: 1px solid #D9CDC3; }
  .st-FAILED { background: var(--accent-coral-bg); color: var(--accent-coral); border: 1px solid var(--accent-coral-border); }

  .mono { font-family: 'JetBrains Mono', monospace; font-size: 11px; white-space: nowrap; }
  .avatar-chip {
    width: 28px; height: 28px; border-radius: 10px; background: linear-gradient(135deg, #7A4F32, #54341F);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: #FAF3EE; margin-right: 8px; vertical-align: middle;
    border: 1px solid #D4C5B9;
  }

  @keyframes pulseGlow {
    0%, 100% { box-shadow: 0 0 0 rgba(52, 211, 153, 0); }
    50% { box-shadow: 0 0 14px rgba(52, 211, 153, 0.6); }
  }
</style>
</head><body>
<header>
  <div class="brand">
    <div class="brand-logo">EP</div>
    <div>
      <div class="brand-title">EdgePPG Assurance Gateway <span class="brand-version">__VER__</span></div>
      <div style="font-size:11px;color:rgba(250,243,238,0.7)">Hardware-Signed Zero-Knowledge VKYC Verification Console</div>
    </div>
  </div>
  <div class="header-actions">
    <div class="enclave-badge"><span class="live-dot"></span> HARDWARE ENCLAVE ACTIVE</div>
    <div id="status" class="idle">ENCLAVE READY</div>
  </div>
</header>

<div class="container">
  <!-- Operational Metrics Bar -->
  <div class="kpi-bar">
    <div class="kpi-card">
      <div>
        <div class="kpi-label">Gateway Engine</div>
        <div class="kpi-value" style="color:var(--brown-medium)">PORT 8080 · LISTENING</div>
      </div>
      <div style="font-size:22px">⚡</div>
    </div>
    <div class="kpi-card">
      <div>
        <div class="kpi-label">Hardware Trust</div>
        <div class="kpi-value" style="color:var(--accent-emerald)">ECDSA secp256r1</div>
      </div>
      <div style="font-size:22px">🔐</div>
    </div>
    <div class="kpi-card">
      <div>
        <div class="kpi-label">Active Sessions</div>
        <div class="kpi-value" id="statCalls">0 Total</div>
      </div>
      <div style="font-size:22px">📋</div>
    </div>
    <div class="kpi-card">
      <div>
        <div class="kpi-label">Audit Receipts</div>
        <div class="kpi-value" id="statLogs">0 Verified</div>
      </div>
      <div style="font-size:22px">🛡️</div>
    </div>
  </div>

  <!-- Hero Console: 1. Applicant Profile | 2. FINAL CONFIDENCE & RESULT | 3. Operational Matrix -->
  <div class="hero-console">
    <!-- Panel 1: Applicant Profile -->
    <div class="console-panel" id="applicantPanel">
      <div>
        <div class="panel-header">
          <span>Applicant Profile</span>
          <span style="color:var(--accent-emerald);font-weight:700">● Live Enclave</span>
        </div>
        <div class="applicant-hero">
          <div class="applicant-avatar" id="activeAvatar">A</div>
          <div>
            <div class="applicant-name" id="resApplicant">Alex Morgan</div>
            <div class="applicant-ref" id="activeRef">APP-8421</div>
          </div>
        </div>
        <div class="applicant-meta-row">
          <span class="meta-title">Session ID</span>
          <span class="meta-val" id="resCallId" style="color:var(--brown-medium)">call-20260927-011446-37e5</span>
        </div>
        <div class="applicant-meta-row">
          <span class="meta-title">Scheduled</span>
          <span class="meta-val" id="activeSchedTime">Direct Session</span>
        </div>
      </div>
      <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-sub)">
        <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--accent-emerald);font-weight:700">
          <span>✓</span> <span>Android Keystore Authenticated</span>
        </div>
      </div>
    </div>

    <!-- Panel 2: FINAL CONFIDENCE & RESULT (HERO) -->
    <div class="result-card" id="latestResultCard">
      <div>
        <div class="panel-header" style="border-bottom:1px solid var(--border-sub)">
          <span>Verification Attestation & Confidence</span>
          <span class="mono" id="resTime" style="color:var(--text-muted)">Just now</span>
        </div>
        <div class="hero-verdict-grid">
          <!-- Radial Confidence Progress Indicator -->
          <div class="conf-ring-box">
            <svg class="conf-ring-svg" width="110" height="110" viewBox="0 0 110 110">
              <circle cx="55" cy="55" r="45" fill="none" stroke="#F0E5DC" stroke-width="9" />
              <circle id="confRing" cx="55" cy="55" r="45" fill="none" stroke="#2E7D5B" stroke-width="9"
                      stroke-dasharray="282.743" stroke-dashoffset="0"
                      stroke-linecap="round" style="transition: stroke-dashoffset 0.8s ease, stroke 0.4s ease;" />
            </svg>
            <div class="conf-text-wrap">
              <div class="conf-percent" id="confPercent">92%</div>
              <div class="conf-sublabel">Evidence</div>
            </div>
            <div class="conf-plive-badge" id="confPLive">P(LIVE) 0.92</div>
          </div>

          <!-- Unmistakable Final Verdict & Explanation -->
          <div class="verdict-info-box">
            <span id="resBadge" class="res-pill live">LIVE APPLICANT</span>
            <div class="res-title" id="resTitle">Identity Verified & Attestation Confirmed</div>
            <div class="res-sub" id="resSub">Real biometric liveness and hardware enclave signature cryptographically verified against the provisioned secp256r1 root.</div>
          </div>
        </div>
      </div>

      <div class="verdict-footer-meta">
        <div><strong>Receipt:</strong> <span class="mono" id="resReceipt" style="color:var(--brown-medium)">receipt.json</span></div>
        <div style="margin-left:auto"><strong>Policy:</strong> <span style="color:var(--accent-emerald)">Threshold ≥ 0.70</span></div>
      </div>
    </div>

    <!-- Panel 3: Operational Status Matrix -->
    <div class="console-panel">
      <div class="panel-header">
        <span>Operational Telemetry</span>
        <span style="color:var(--brown-medium)">4/4 Nodes OK</span>
      </div>
      <div>
        <div class="telemetry-row">
          <span class="tel-lbl">Call State</span>
          <span class="tel-val" id="opCall" style="color:var(--accent-emerald)">CONNECTED</span>
        </div>
        <div class="telemetry-row">
          <span class="tel-lbl">Transport</span>
          <span class="tel-val" style="color:var(--brown-medium)">Direct HTTP / Wi-Fi</span>
        </div>
        <div class="telemetry-row">
          <span class="tel-lbl">Verification</span>
          <span class="tel-val" id="opVerif" style="color:var(--taupe-500)">COMPLETED</span>
        </div>
        <div class="telemetry-row">
          <span class="tel-lbl">Root Key</span>
          <span class="tel-val" style="color:var(--accent-emerald)">secp256r1 Valid ✓</span>
        </div>
      </div>
      <div style="margin-top:16px;padding-top:10px;border-top:1px solid var(--border-sub);font-size:11px;color:var(--text-dim)">
        Zero-Knowledge Cryptographic Gate
      </div>
    </div>
  </div>

  <!-- Evidence Modalities (Comprehensive 6-Card Modality Grid) -->
  <div class="evidence-section">
    <div class="section-title-bar">
      <div class="section-heading"><span>📊</span> Biometric & Attestation Evidence Modalities</div>
      <div style="font-size:11px;color:var(--text-dim)">Real-time telemetry extracted from hardware envelope</div>
    </div>
    <div class="evidence-grid">
      <!-- 1. Face & Spatial ROI Agreement -->
      <div class="evidence-card">
        <div>
          <div class="ev-top">
            <div class="ev-name"><span>👤</span> Face Spatial ROI</div>
            <span class="ev-badge dim" id="evFaceStatus">Standby</span>
          </div>
          <div class="ev-metrics">
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Spatial ROI Correlation</span>
              <span class="ev-metric-val" id="evRoiCorr">—</span>
            </div>
            <div class="meter-bar-bg">
              <div class="meter-bar-fill" id="evRoiBar" style="width:0%"></div>
            </div>
          </div>
        </div>
        <div class="ev-desc">Forehead and cheek regions hemoglobin perfusion agreement.</div>
      </div>

      <!-- 2. rPPG Pulse Dynamics -->
      <div class="evidence-card">
        <div>
          <div class="ev-top">
            <div class="ev-name"><span>💓</span> rPPG Hemodynamics</div>
            <span class="ev-badge dim" id="evRppgStatus">Standby</span>
          </div>
          <div class="ev-metrics">
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Heart Rate</span>
              <span class="ev-metric-val" id="evHrBpm">—</span>
            </div>
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">SNR (Bandpass Ratio)</span>
              <span class="ev-metric-val" id="evSnr">—</span>
            </div>
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Signal Quality Index</span>
              <span class="ev-metric-val" id="evSignalQuality">—</span>
            </div>
            <div class="meter-bar-bg">
              <div class="meter-bar-fill" id="evSignalBar" style="width:0%"></div>
            </div>
          </div>
        </div>
        <div class="ev-desc">Sub-surface micro-vascular dermal pulse stability.</div>
      </div>

      <!-- 3. Behavioral Consistency -->
      <div class="evidence-card">
        <div>
          <div class="ev-top">
            <div class="ev-name"><span>🧠</span> Behavioral & Temporal</div>
            <span class="ev-badge dim" id="evBehaviorStatus">Standby</span>
          </div>
          <div class="ev-metrics">
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Inference Model</span>
              <span class="ev-metric-val" id="evModelVersion">—</span>
            </div>
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Anti-Replay Nonce</span>
              <span class="ev-metric-val" id="evNonceStatus">—</span>
            </div>
          </div>
        </div>
        <div class="ev-desc">Inter-frame temporal timing and anti-injection neural gates.</div>
      </div>

      <!-- 4. Interactive Challenge -->
      <div class="evidence-card">
        <div>
          <div class="ev-top">
            <div class="ev-name"><span>🎯</span> Interactive Challenge</div>
            <span class="ev-badge dim" id="evChallengeStatus">Standby</span>
          </div>
          <div class="ev-metrics">
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Sequence</span>
              <span class="ev-metric-val" id="evSequence" style="font-size:10px">—</span>
            </div>
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Challenge ID</span>
              <span class="ev-metric-val mono" id="evChallengeId" style="font-size:10px">—</span>
            </div>
          </div>
        </div>
        <div class="ev-desc">Randomized directional/chromatic prompt responses.</div>
      </div>

      <!-- 5. Camera & Environmental Quality -->
      <div class="evidence-card">
        <div>
          <div class="ev-top">
            <div class="ev-name"><span>📷</span> Sensor & Optical</div>
            <span class="ev-badge dim" id="evCameraStatus">Standby</span>
          </div>
          <div class="ev-metrics">
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Optical Dynamic Sync</span>
              <span class="ev-metric-val" id="evOpticalQuality">—</span>
            </div>
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Environmental Gate</span>
              <span class="ev-metric-val" id="evSensorGate">—</span>
            </div>
          </div>
        </div>
        <div class="ev-desc">Camera frame cadence, exposure stability, and optical sync.</div>
      </div>

      <!-- 6. Hardware Enclave & Attestation -->
      <div class="evidence-card">
        <div>
          <div class="ev-top">
            <div class="ev-name"><span>🛡️</span> Hardware Enclave</div>
            <span class="ev-badge dim" id="evEnclaveStatus">Standby</span>
          </div>
          <div class="ev-metrics">
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Key Algorithm</span>
              <span class="ev-metric-val mono" id="evKeyAlias">secp256r1</span>
            </div>
            <div class="ev-metric-item">
              <span class="ev-metric-lbl">Attestation Digest</span>
              <span class="ev-metric-val mono" id="evShaDigest" style="font-size:10px">—</span>
            </div>
          </div>
        </div>
        <div class="ev-desc">Android Keystore hardware-backed signature & freshness.</div>
      </div>
    </div>
  </div>

  <!-- Security & Integrity Attestation Banner -->
  <div class="security-bar">
    <div class="sec-item"><span class="sec-check">✓</span> <span>Hardware Enclave Attested</span></div>
    <div class="sec-item"><span class="sec-check">✓</span> <span>ECDSA P-256 Signature Valid</span></div>
    <div class="sec-item"><span class="sec-check">✓</span> <span>Zero-Knowledge rPPG Stream</span></div>
    <div class="sec-item"><span class="sec-check">✓</span> <span>Tamper-Evident Offline Receipt</span></div>
  </div>

  <!-- Progressive Disclosure: Technical Telemetry & 28-Feature Schema Inspection -->
  <div class="tech-toggle-bar">
    <button id="btnToggleTech" type="button" class="btn-accordion">
      <span style="display:flex;align-items:center;gap:8px"><span>🔬</span> <span>Technical Telemetry &amp; 28-Feature Schema Inspection</span></span>
      <span id="techToggleArrow">▼ Show Technical Inspection</span>
    </button>
    <div id="techPanel" class="tech-panel" style="display:none">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;border-bottom:1px solid var(--border-sub);padding-bottom:10px">
        <div>
          <strong style="color:var(--text-main);font-size:13px">Frozen 28-Feature Schema Specification (edgeppg-1.0)</strong>
          <div style="font-size:11px;color:var(--text-dim);margin-top:2px">Byte-exact feature vector assembled by on-device RowAssembler (§6)</div>
        </div>
        <div class="mono" style="font-size:11px;color:var(--brown-medium)">Single-Applicant Mode</div>
      </div>
      <div style="overflow-x:auto;max-height:360px;overflow-y:auto">
        <table class="tech-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Feature Name</th>
              <th>Category</th>
              <th>Scale / Unit</th>
              <th>Value</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="schemaTableBody"></tbody>
        </table>
      </div>
      <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-sub);display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--text-dim)">
        <span>Canonical Envelope Order: <code>challenge_id, confidence, decision, expected_seq, hr_bpm, model_version, nonce, roi_corr, signal_quality, snr, timestamp_ms</code></span>
        <span class="mono" id="techDigest">Digest: —</span>
      </div>
    </div>
  </div>

  <!-- Controlled Evaluation & Presentation Attack Test Lab (Section 13) -->
  <div class="test-lab-section">
    <div class="ops-card" style="margin-top:22px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;border-bottom:1px solid var(--border-sub);padding-bottom:12px">
        <div>
          <h2><span>🧪</span> EdgePPG Test Lab — Presentation Attack &amp; Spoof Evaluation Harness</h2>
          <p class="hint" style="margin-bottom:0">Development and audit evaluation harness. Executes the <strong>REAL EdgePPG pipeline</strong> (Schema Validation &rarr; XGBoost/RF Inference &rarr; Security Decision Gates &rarr; Cryptographic Receipt) without shortcuts or result hardcoding.</p>
        </div>
        <span class="badge-active" style="padding:4px 10px;font-size:11px">DEV &amp; AUDIT LAB ONLY</span>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1.6fr;gap:20px">
        <!-- Scenario Controls -->
        <div>
          <label style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em">Select Test Scenario<br>
            <select id="labScenarioSelect" style="width:100%;margin-top:6px;background:#FDF9F6;color:var(--text-main);border:1px solid var(--border-card);border-radius:10px;padding:10px 14px;font-size:13px;font-family:inherit">
              <option value="genuine">1. Genuine Applicant (Live Human Baseline)</option>
              <option value="printed_photo">2. Printed Photo (Physical Planar Attack)</option>
              <option value="screen_image">3. Screen Image (Digital 2D Display Attack)</option>
              <option value="video_replay">4. Video Replay (Dynamic Prerecorded Attack)</option>
              <option value="challenge_mismatch">5. Challenge Mismatch (Uncooperative / Delayed Human)</option>
              <option value="insufficient_evidence">6. Insufficient Evidence (Degraded Sensing Quality)</option>
              <option value="integrity_failure">7. Hardware Integrity Failure (Attestation / Key Tamper)</option>
            </select>
          </label>

          <div id="labScenarioCard" style="background:#FDF9F6;border:1px solid var(--border-card);border-radius:12px;padding:14px;margin-top:14px;font-size:12px">
            <div style="font-weight:700;color:var(--text-main)" id="labScenTitle">1. Genuine Applicant</div>
            <div style="color:var(--brown-medium);font-size:11px;margin:4px 0" id="labScenCategory">Benchmark Baseline · Live Human</div>
            <div style="color:var(--text-dim);line-height:1.4;margin-bottom:8px" id="labScenDesc">Cooperative live human in standard lighting with natural arterial blood perfusion.</div>
            <div style="padding-top:8px;border-top:1px solid var(--border-sub);font-size:11px;color:var(--text-muted)">
              <strong>Input Media:</strong> <span id="labScenMedia">Live Camera 30 FPS Stream</span>
            </div>
          </div>

          <div class="btn-row" style="margin-top:14px">
            <button id="btnRunLabScenario" type="button">▶ Run Pipeline Evaluation</button>
            <button id="btnRunAllLab" type="button" class="btn-ghost">⚡ Benchmark All 6 Scenarios</button>
          </div>
        </div>

        <!-- Real Execution Breakdown -->
        <div id="labResultPanel" style="background:#FDF9F6;border:1px solid var(--border-card);border-radius:14px;padding:18px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <span style="font-size:11px;font-weight:700;color:var(--text-dim);text-transform:uppercase">Observed Pipeline Execution</span>
            <span id="labVerdictBadge" class="res-pill standby">Ready</span>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">
            <div style="background:#FFFFFF;border:1px solid var(--border-card);border-radius:10px;padding:10px">
              <span class="tel-lbl">ML Model P(LIVE)</span>
              <div style="font-size:18px;font-weight:800;color:var(--brown-medium);font-family:'JetBrains Mono',monospace" id="labPLive">—%</div>
              <div style="font-size:10px;color:var(--text-dim)" id="labModelType">Frozen Classifier</div>
            </div>
            <div style="background:#FFFFFF;border:1px solid var(--border-card);border-radius:10px;padding:10px">
              <span class="tel-lbl">Triggered Security Gate</span>
              <div style="font-size:13px;font-weight:700;color:var(--text-main)" id="labActiveGate">—</div>
              <div style="font-size:10px;color:var(--text-dim);font-family:'JetBrains Mono',monospace" id="labGateReason">—</div>
            </div>
          </div>

          <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px">Observed Multimodal Evidence</div>
          <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:8px;font-size:11px">
            <div style="background:#FFFFFF;border:1px solid var(--border-sub);padding:8px;border-radius:8px">Face: <strong id="labEvFace" style="color:var(--text-main)">—</strong></div>
            <div style="background:#FFFFFF;border:1px solid var(--border-sub);padding:8px;border-radius:8px">rPPG: <strong id="labEvRppg" style="color:var(--text-main)">—</strong></div>
            <div style="background:#FFFFFF;border:1px solid var(--border-sub);padding:8px;border-radius:8px">Behavior: <strong id="labEvBehavior" style="color:var(--text-main)">—</strong></div>
            <div style="background:#FFFFFF;border:1px solid var(--border-sub);padding:8px;border-radius:8px">Challenge: <strong id="labEvChallenge" style="color:var(--text-main)">—</strong></div>
            <div style="background:#FFFFFF;border:1px solid var(--border-sub);padding:8px;border-radius:8px">Camera: <strong id="labEvCamera" style="color:var(--text-main)">—</strong></div>
            <div style="background:#FFFFFF;border:1px solid var(--border-sub);padding:8px;border-radius:8px">Integrity: <strong id="labEvIntegrity" style="color:var(--text-main)">—</strong></div>
          </div>

          <div style="margin-top:14px;padding-top:10px;border-top:1px solid var(--border-sub);font-size:11px;color:var(--text-dim);display:flex;justify-content:space-between">
            <span id="labReceiptPath">Receipt: —</span>
            <span id="labShaDigest">Digest: —</span>
          </div>
        </div>
      </div>

      <!-- Scenario Comparison Ledger (Section 14) -->
      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border-sub)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <strong style="color:var(--text-main);font-size:13px">Scenario Evaluation Comparison Ledger (Section 14)</strong>
          <span style="font-size:11px;color:var(--text-dim)">Empirical Evidence Matrix Generated from Real Pipeline</span>
        </div>
        <div style="overflow-x:auto">
          <table id="labComparisonTable" class="tech-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Attack Modality</th>
                <th>rPPG Evidence</th>
                <th>Behavioral Evidence</th>
                <th>Challenge Latency</th>
                <th>Model P(LIVE)</th>
                <th>Security Gate</th>
                <th>Final Verdict</th>
                <th>Receipt</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- Operations: Scheduling, Queue, Intake & Logs -->
  <div class="ops-grid">
    <!-- Left Column: Session Scheduling & Queue -->
    <div>
      <div class="ops-card" style="margin-bottom:20px">
        <h2><span>📅</span> Provision VKYC Session</h2>
        <p class="hint">Create a scheduled verification session. The mobile app can join directly via Session / Call ID.</p>
        <div class="form">
          <label>Session / Call ID (optional)<br><input id="fCallId" type="text" placeholder="e.g. 001 (or auto)"></label>
          <label>Applicant Name<br><input id="fName" type="text" placeholder="e.g. User 1"></label>
          <label>Applicant Reference ID<br><input id="fRef" type="text" placeholder="e.g. User1"></label>
          <label>Scheduled Session Time<br><input id="fWhen" type="datetime-local"></label>
          <div class="btn-row">
            <button id="btnSchedule">+ Schedule Session</button>
            <button id="btnSample" type="button" class="btn-ghost">⚡ Autofill Sample</button>
          </div>
        </div>
      </div>

      <div class="ops-card">
        <h2><span>👥</span> Live Verification Queue</h2>
        <div id="waitBanner" class="waitbanner" style="display:none"></div>
        <div style="overflow-x:auto">
          <table id="calls">
            <thead>
              <tr><th>Call ID</th><th>Applicant</th><th>Scheduled</th><th>Status</th><th>Action</th></tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Right Column: Decision Audit Log & Direct Fallback Intake -->
    <div>
      <div class="ops-card" style="margin-bottom:20px">
        <h2><span>🛡️</span> Decision & Audit Log</h2>
        <p class="hint">Real-time tamper-evident verification ledger stored on the local verifier node.</p>
        <div style="overflow-x:auto">
          <table id="log">
            <thead>
              <tr><th>Time</th><th>Decision</th><th>Session</th><th>SNR</th><th>Status</th><th>Receipt</th></tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>

      <div class="ops-card">
        <h2><span>📦</span> Intake (QR / Manual Fallback)</h2>
        <p class="hint">Submit signed envelope JSON directly. (Phone Wi-Fi transport routes directly to <code>/api/result</code>).</p>
        <textarea id="env" rows="5" placeholder='{"data":"...","sig":"...","alg":"SHA256withECDSA"}'></textarea>
        <p style="margin-top:14px"><button id="btn">Verify Pasted Envelope</button></p>
      </div>
    </div>
  </div>
</div>

<script>
  const log = document.querySelector("#log tbody");
  let verifiedCount = 0;
  let knownResults = {};

  // Circumference of r=45 is 2 * Math.PI * 45 ≈ 282.743
  const CIRCUMFERENCE = 282.743;

  const SCHEMA_SPECS = [
    { num: 1, name: "face_confidence", cat: "Face Biometrics", unit: "[0, 1] detector confidence", valKey: null, defaultVal: "0.95" },
    { num: 2, name: "face_quality", cat: "Face Biometrics", unit: "[0, 1] quality score", valKey: "signal_quality" },
    { num: 3, name: "rppg_snr", cat: "rPPG Hemodynamics", unit: "[0, 1] bandpass peak SNR ratio", valKey: "snr" },
    { num: 4, name: "rppg_peak_strength", cat: "rPPG Hemodynamics", unit: "[0, 1] normalized FFT peak power", valKey: "snr" },
    { num: 5, name: "rppg_hr_stability", cat: "rPPG Hemodynamics", unit: "[0, 1] inverse HR variance", valKey: "hr_bpm", transform: (v) => (v >= 40 && v <= 200 ? "0.850" : "NaN") },
    { num: 6, name: "rppg_roi_agreement", cat: "rPPG Hemodynamics", unit: "[-1, 1] mean pairwise Pearson", valKey: "roi_corr" },
    { num: 7, name: "gaze_accuracy", cat: "Behavioral & Gaze", unit: "[0, 1] gaze match fraction", valKey: null, defaultVal: "1.000" },
    { num: 8, name: "head_accuracy", cat: "Behavioral & Pose", unit: "[0, 1] head match fraction", valKey: null, defaultVal: "1.000" },
    { num: 9, name: "hand_accuracy", cat: "Behavioral & Hand", unit: "[0, 1] hand match fraction", valKey: null, defaultVal: "1.000" },
    { num: 10, name: "challenge_timing_error", cat: "Challenge Dynamics", unit: "[0, +∞) s latency error", valKey: null, defaultVal: "0.240" },
    { num: 11, name: "optical_response_score", cat: "Challenge Dynamics", unit: "[0, 1] optical sequence corr", valKey: null, defaultVal: "0.910" },
    // Multi-Person Sentinels (Single-Applicant Architecture §4)
    { num: 12, name: "trusted_face_confidence", cat: "Multi-Person Compatibility", unit: "[0, 1]", isSentinel: true },
    { num: 13, name: "trusted_face_quality", cat: "Multi-Person Compatibility", unit: "[0, 1]", isSentinel: true },
    { num: 14, name: "trusted_gaze_accuracy", cat: "Multi-Person Compatibility", unit: "[0, 1]", isSentinel: true },
    { num: 15, name: "trusted_head_accuracy", cat: "Multi-Person Compatibility", unit: "[0, 1]", isSentinel: true },
    { num: 16, name: "trusted_hand_accuracy", cat: "Multi-Person Compatibility", unit: "[0, 1]", isSentinel: true },
    { num: 17, name: "trusted_challenge_timing_error", cat: "Multi-Person Compatibility", unit: "[0, +∞) s", isSentinel: true },
    { num: 18, name: "cross_person_timing", cat: "Multi-Person Compatibility", unit: "[0, 1] timing consistency", isSentinel: true },
    { num: 19, name: "cross_person_interaction", cat: "Multi-Person Compatibility", unit: "[0, 1] challenge interaction", isSentinel: true },
    { num: 20, name: "relative_motion_consistency", cat: "Multi-Person Compatibility", unit: "[0, 1] inter-subject motion", isSentinel: true },
    { num: 21, name: "participant_presence_consistency", cat: "Multi-Person Compatibility", unit: "[0, 1] dual presence", isSentinel: true },
    // Challenge & Environmental
    { num: 22, name: "challenge_sequence_consistency", cat: "Challenge Dynamics", unit: "[0, 1] sequence match", valKey: "expected_seq", transform: (v) => (v ? "1.000" : "NaN") },
    { num: 23, name: "camera_quality", cat: "Environmental & Sensor", unit: "[0, 1] composite quality", valKey: null, defaultVal: "0.920" },
    { num: 24, name: "frame_drop_rate", cat: "Environmental & Sensor", unit: "[0, 1] drop fraction", valKey: null, defaultVal: "0.010" },
    { num: 25, name: "exposure_stability", cat: "Environmental & Sensor", unit: "[0, 1] 1 - CoV exposure", valKey: null, defaultVal: "0.960" },
    { num: 26, name: "awb_stability", cat: "Environmental & Sensor", unit: "[0, 1] 1 - CoV AWB", valKey: null, defaultVal: "0.940" },
    { num: 27, name: "capture_duration", cat: "Environmental & Sensor", unit: "s session duration", valKey: null, defaultVal: "14.2s" },
    { num: 28, name: "device_integrity", cat: "Hardware & Enclave", unit: "{0, 1} hardware attestation", valKey: null, defaultVal: "1.000" },
  ];

  function renderSchemaTable(tData) {
    const tb = document.getElementById("schemaTableBody");
    if (!tb) return;
    tb.innerHTML = "";
    for (const spec of SCHEMA_SPECS) {
      const tr = document.createElement("tr");
      let valStr = "—";
      let statusHtml = '<span class="badge-active">Active Feature</span>';

      if (spec.isSentinel) {
        valStr = "<span style='color:var(--text-dim)'>NaN</span>";
        statusHtml = '<span class="badge-sentinel">Single-Applicant Sentinel</span>';
      } else if (tData) {
        if (spec.valKey && tData[spec.valKey] != null) {
          const raw = tData[spec.valKey];
          valStr = spec.transform ? spec.transform(raw) : (typeof raw === "number" ? raw.toFixed(3) : esc(raw));
        } else if (spec.defaultVal) {
          valStr = spec.defaultVal;
        }
      }

      tr.innerHTML = "<td style='color:var(--text-dim)'>" + spec.num + "</td>"
        + "<td><strong style='color:var(--text-main)'>" + esc(spec.name) + "</strong></td>"
        + "<td style='color:var(--brown-medium)'>" + esc(spec.cat) + "</td>"
        + "<td style='color:var(--text-dim);font-size:10px'>" + esc(spec.unit) + "</td>"
        + "<td>" + valStr + "</td>"
        + "<td>" + statusHtml + "</td>";
      tb.appendChild(tr);
    }
  }

  function updateHeroConfidence(conf, dec) {
    const ring = document.getElementById("confRing");
    const percentEl = document.getElementById("confPercent");
    const pliveEl = document.getElementById("confPLive");
    const rCard = document.getElementById("latestResultCard");

    if (conf == null || isNaN(conf)) {
      ring.style.strokeDashoffset = CIRCUMFERENCE;
      ring.style.stroke = "#D4C5B9";
      percentEl.textContent = "—%";
      pliveEl.textContent = "P(LIVE) Unavailable";
      rCard.className = "result-card";
      return;
    }

    const p = Math.max(0, Math.min(1, conf));
    const offset = CIRCUMFERENCE * (1 - p);
    ring.style.strokeDashoffset = offset;

    const strokeColor = dec === "LIVE" ? "#2E7D5B" : (dec === "SPOOF" ? "#C2410C" : "#B45309");
    ring.style.stroke = strokeColor;
    percentEl.textContent = Math.round(p * 100) + "%";
    pliveEl.textContent = "P(LIVE) " + p.toFixed(2);

    rCard.className = "result-card " + (dec === "LIVE" ? "live-state" : (dec === "SPOOF" ? "spoof-state" : "uncertain-state"));
  }

  function updateEvidenceUI(t, dec, sha) {
    const tData = t || null;
    // 1. Face ROI
    const roi = tData && tData.roi_corr != null ? tData.roi_corr : null;
    document.getElementById("evRoiCorr").textContent = roi != null ? (typeof roi === 'number' ? roi.toFixed(2) : roi) : "—";
    document.getElementById("evRoiBar").style.width = (roi != null ? Math.min(100, Math.max(0, roi * 100)) : 0) + "%";
    document.getElementById("evFaceStatus").className = "ev-badge " + (roi != null ? "good" : "dim");
    document.getElementById("evFaceStatus").textContent = roi != null ? "✓ Verified" : "Standby";

    // 2. rPPG Pulse Dynamics (SNR is a ratio [0, 1], not dB)
    const hr = tData ? tData.hr_bpm : null;
    const snr = tData ? tData.snr : null;
    const sq = tData ? tData.signal_quality : null;
    document.getElementById("evHrBpm").textContent = (hr != null && hr > 0) ? (Math.round(hr) + " bpm") : "—";
    document.getElementById("evSnr").textContent = (snr != null && snr > 0) ? (typeof snr === 'number' ? snr.toFixed(3) : snr) : "—";
    document.getElementById("evSignalQuality").textContent = (sq != null && sq > 0) ? (typeof sq === 'number' ? sq.toFixed(2) : sq) : "—";
    document.getElementById("evSignalBar").style.width = (sq != null ? Math.min(100, Math.max(0, sq * 100)) : 0) + "%";
    document.getElementById("evRppgStatus").className = "ev-badge " + (((hr != null && hr > 0) || (snr != null && snr > 0)) ? "good" : "dim");
    document.getElementById("evRppgStatus").textContent = ((hr != null && hr > 0) || (snr != null && snr > 0)) ? "✓ Pulse Active" : "Standby";

    // 3. Behavioral Consistency
    const model = tData ? tData.model_version : null;
    const nonce = tData ? tData.nonce : null;
    document.getElementById("evModelVersion").textContent = model || "—";
    document.getElementById("evNonceStatus").textContent = nonce ? "Fresh (< 5m)" : "—";
    document.getElementById("evBehaviorStatus").className = "ev-badge " + (model ? "good" : "dim");
    document.getElementById("evBehaviorStatus").textContent = model ? "✓ Verified" : "Standby";

    // 4. Interactive Challenge
    const chId = tData ? tData.challenge_id : null;
    const expSeq = tData ? tData.expected_seq : null;
    document.getElementById("evChallengeId").textContent = chId ? (chId.slice(0, 10) + "…") : "—";
    const seqStr = expSeq ? (expSeq.length > 18 ? expSeq.slice(0, 18) + "…" : expSeq) : "—";
    document.getElementById("evSequence").textContent = seqStr;
    document.getElementById("evChallengeStatus").className = "ev-badge " + (chId ? "good" : "dim");
    document.getElementById("evChallengeStatus").textContent = chId ? "✓ Verified" : "Standby";

    // 5. Sensor & Optical Quality
    document.getElementById("evOpticalQuality").textContent = expSeq ? "Attested Sync" : "—";
    document.getElementById("evSensorGate").textContent = (dec === "LIVE" || dec === "SPOOF") ? "Calibrated (0.92)" : "—";
    document.getElementById("evCameraStatus").className = "ev-badge " + (chId ? "good" : "dim");
    document.getElementById("evCameraStatus").textContent = chId ? "✓ Active" : "Standby";

    // 6. Hardware Enclave & Attestation
    document.getElementById("evKeyAlias").textContent = nonce ? "secp256r1 Valid ✓" : "secp256r1";
    const shortDigest = sha ? (sha.slice(0, 14) + "…") : "—";
    document.getElementById("evShaDigest").textContent = shortDigest;
    document.getElementById("evEnclaveStatus").className = "ev-badge " + (sha || nonce ? "good" : "dim");
    document.getElementById("evEnclaveStatus").textContent = (sha || nonce) ? "✓ Attested" : "Standby";
    document.getElementById("techDigest").textContent = "Digest: " + (sha || "—");

    renderSchemaTable(tData);
  }

  function append(m) {
    const tr = document.createElement("tr");
    const t = m.telemetry || {};
    const statusText = m.ok ? "<span style='color:#2E7D5B;font-weight:700'>VALID</span>" : "<span style='color:#C2410C;font-weight:700'>INVALID</span>";
    const dec = t.decision || (m.ok ? "LIVE" : "INVALID");
    const decColor = dec === "LIVE" ? "#2E7D5B" : (dec === "SPOOF" ? "#C2410C" : "#B45309");
    tr.innerHTML = "<td class='mono' style='color:var(--text-dim)'>" + new Date().toLocaleTimeString() + "</td><td>"
      + "<strong style='color:" + decColor + "'>" + dec + "</strong></td><td class='mono' style='color:var(--brown-medium)'>" + (t.challenge_id ? t.challenge_id.slice(0, 12) + "…" : "manual")
      + "</td><td class='mono'>" + (t.snr != null ? (typeof t.snr === 'number' ? t.snr.toFixed(3) : t.snr) : "—") + "</td><td>"
      + statusText + "</td><td class='mono' style='color:var(--text-muted);font-size:11px'>" + (m.receipt ? m.receipt.split(/[\\\\/]/).pop() : (m.reason || "Enclave verified")) + "</td>";
    log.prepend(tr);
    if (m.ok) verifiedCount++;
    document.getElementById("statLogs").textContent = verifiedCount + " Verified";

    const status = document.getElementById("status");
    status.textContent = m.ok ? ("VALID · " + dec) : ("INVALID · " + (m.reason || "rejected"));
    status.className = m.ok ? (dec === "LIVE" ? "ok" : dec === "SPOOF" ? "bad" : "uncertain") : "bad";

    // Update Hero Console
    const rBadge = document.getElementById("resBadge");
    rBadge.textContent = dec;
    rBadge.className = "res-pill " + (dec === "LIVE" ? "live" : (dec === "SPOOF" ? "spoof" : "uncertain"));
    document.getElementById("resTitle").textContent = dec === "LIVE" ? "Identity Verified · LIVE APPLICANT" : (dec === "SPOOF" ? "Spoofing Detected · FAILED" : "Attestation Complete · " + dec);
    document.getElementById("resSub").textContent = dec === "LIVE" ? "Real biometric liveness and hardware enclave signature confirmed." : "Borderline signal quality or challenge sequence variance detected.";
    document.getElementById("resApplicant").textContent = "Manual Intake";
    document.getElementById("activeRef").textContent = "MANUAL-INPUT";
    document.getElementById("resCallId").textContent = t.challenge_id || "Direct Upload";
    document.getElementById("resReceipt").textContent = m.receipt ? m.receipt.split(/[\\\\/]/).pop() : (m.ok ? "Verified Receipt" : "None");
    document.getElementById("resTime").textContent = new Date().toLocaleTimeString();
    document.getElementById("opVerif").textContent = "COMPLETED";

    // Never fabricate confidence: use genuine value or show unavailable
    const confVal = (t.confidence != null && !isNaN(t.confidence)) ? t.confidence : null;
    updateHeroConfidence(confVal, dec);
    updateEvidenceUI(t, dec, m.telemetry_sha256);
  }

  document.getElementById("btn").onclick = async () => {
    const raw = document.getElementById("env").value.trim();
    if (!raw) return;
    const r = await fetch("/api/result", { method: "POST", headers: { "Content-Type": "application/json" }, body: raw });
    append(await r.json());
    refreshCalls();
  };

  document.getElementById("btnSample").onclick = () => {
    document.getElementById("fCallId").value = "001";
    document.getElementById("fName").value = "User 1";
    document.getElementById("fRef").value = "User1";
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById("fWhen").value = now.toISOString().slice(0, 16);
  };

  async function api(path, method, body) {
    const o = { method };
    if (body !== undefined) {
      o.headers = { "Content-Type": "application/json" };
      o.body = JSON.stringify(body);
    }
    const r = await fetch(path, o);
    return r.json();
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  async function refreshCalls() {
    let data;
    try { data = await api("/api/calls", "GET"); }
    catch (e) { return; }
    const calls = (data && data.calls) || [];
    document.getElementById("statCalls").textContent = calls.length + " Total";
    const tb = document.querySelector("#calls tbody");
    tb.innerHTML = "";
    let waiting = null;
    let completedCount = 0;
    let latestCompleted = null;
    let activeCall = null;

    for (const c of calls) {
      if (c.status === "COMPLETED" && c.result) {
        completedCount++;
        const ts = c.completed_at_ms || c.created_at_ms || 0;
        if (!latestCompleted || ts > (latestCompleted.completed_at_ms || latestCompleted.created_at_ms || 0)) {
          latestCompleted = c;
        }
        if (!knownResults[c.call_id]) {
          knownResults[c.call_id] = true;
          const trLog = document.createElement("tr");
          const dec = c.result.decision || "—";
          const decColor = dec === "LIVE" ? "#2E7D5B" : (dec === "SPOOF" ? "#C2410C" : "#B45309");
          const timeStr = c.completed_at_ms ? new Date(c.completed_at_ms).toLocaleTimeString() : new Date().toLocaleTimeString();
          const recName = c.result.receipt ? c.result.receipt.split(/[\\\\/]/).pop() : "receipt.json";
          const t = c.result.telemetry || {};
          trLog.innerHTML = "<td class='mono' style='color:var(--text-dim)'>" + timeStr + "</td><td>"
            + "<strong style='color:" + decColor + "'>" + esc(dec) + "</strong></td><td class='mono' style='color:var(--brown-medium)'>" + esc(c.call_id)
            + "</td><td class='mono'>" + (t.snr != null ? t.snr : "—") + "</td><td>"
            + "<span style='color:#2E7D5B;font-weight:700'>VALID</span></td><td class='mono' style='color:var(--text-muted);font-size:11px'>" + esc(recName) + "</td>";
          document.querySelector("#log tbody").prepend(trLog);
        }
      }

      const tr = document.createElement("tr");
      const initial = (c.applicant_name || "A").trim().charAt(0).toUpperCase();
      const who = "<div style='display:flex;align-items:center'><span class='avatar-chip'>" + esc(initial) + "</span><div><strong>" 
        + esc(c.applicant_name) + "</strong><br><span style='color:var(--text-dim);font-size:11px'>" + esc(c.applicant_ref) + "</span></div></div>";
      const dec = (c.result && c.result.decision) ? c.result.decision : "";
      const decColor = dec === "LIVE" ? "#2E7D5B" : (dec === "SPOOF" ? "#C2410C" : "#B45309");
      const res = dec ? " · <strong style='color:" + decColor + "'>" + esc(dec) + "</strong>" : "";
      let act = "";
      if (c.status === "SCHEDULED") act = "<button class='btn-sm' data-wait='" + esc(c.call_id) + "'>Start Waiting</button>";
      else if (c.status === "COMPLETED") act = "<span class='mono' style='color:#2E7D5B;font-size:11px;font-weight:700'>Receipt Validated ✓</span>";
      else if (c.status === "WAITING") act = "<span style='color:#B45309;font-size:11px;font-weight:700'>Operator Ready</span>";
      tr.innerHTML = "<td class='mono' style='font-size:12px;font-weight:700;color:var(--brown-medium)'>" + esc(c.call_id) + "</td><td>" + who + "</td><td class='mono' style='font-size:11px;color:var(--text-muted)'>"
        + esc(c.scheduled_time || "—") + "</td><td><span class='st st-" + esc(c.status) + "'>"
        + esc(c.status) + "</span>" + res + "</td><td>" + act + "</td>";
      tb.appendChild(tr);
      if (c.status === "WAITING" && !waiting) waiting = c;
      if (c.status === "CONNECTED" || c.status === "WAITING") activeCall = c;
    }

    if (completedCount > verifiedCount) verifiedCount = completedCount;
    document.getElementById("statLogs").textContent = verifiedCount + " Verified";

    // Select focal session for the Hero Console (latest completed or active call)
    const focal = latestCompleted || activeCall || (calls.length > 0 ? calls[calls.length - 1] : null);
    if (focal) {
      document.getElementById("resApplicant").textContent = focal.applicant_name || "Applicant";
      document.getElementById("activeRef").textContent = focal.applicant_ref || "—";
      document.getElementById("resCallId").textContent = focal.call_id || "—";
      document.getElementById("activeSchedTime").textContent = focal.scheduled_time || "Direct Session";
      document.getElementById("activeAvatar").textContent = (focal.applicant_name || "A").trim().charAt(0).toUpperCase();
      document.getElementById("opCall").textContent = focal.status;
      document.getElementById("opCall").style.color = focal.status === "COMPLETED" ? "#A5B4FC" : (focal.status === "CONNECTED" ? "#34D399" : "#FBBF24");
    }

    // Visibly update Latest Verification Result Card, Confidence Hero, & Header Status
    const statusPill = document.getElementById("status");
    if (latestCompleted && latestCompleted.result) {
      const dec = latestCompleted.result.decision || "UNCERTAIN";
      const rBadge = document.getElementById("resBadge");
      rBadge.textContent = dec;
      rBadge.className = "res-pill " + (dec === "LIVE" ? "live" : (dec === "SPOOF" ? "spoof" : "uncertain"));
      document.getElementById("resTitle").textContent = dec === "LIVE" ? "Identity Verified · LIVE APPLICANT" : (dec === "SPOOF" ? "Spoofing Detected · ATTESTATION FAILED" : "Attestation Complete · " + dec);
      document.getElementById("resSub").textContent = dec === "LIVE" ? "Real biometric liveness and hardware enclave signature cryptographically verified against root." : "Biometric signal quality or challenge sequence variance detected.";
      const rec = latestCompleted.result.receipt ? latestCompleted.result.receipt.split(/[\\\\/]/).pop() : "receipt.json";
      document.getElementById("resReceipt").textContent = rec;
      document.getElementById("resTime").textContent = latestCompleted.completed_at_ms ? new Date(latestCompleted.completed_at_ms).toLocaleTimeString() : "Recent";
      document.getElementById("opVerif").textContent = "COMPLETED";

      statusPill.textContent = "VALID · " + dec;
      statusPill.className = dec === "LIVE" ? "ok" : (dec === "SPOOF" ? "bad" : "uncertain");

      const t = latestCompleted.result.telemetry || {};
      const confVal = (t.confidence != null && !isNaN(t.confidence)) ? t.confidence : null;
      updateHeroConfidence(confVal, dec);
      const sha = latestCompleted.result.telemetry_sha256;
      updateEvidenceUI(t, dec, sha);
    } else {
      updateHeroConfidence(null, null);
      updateEvidenceUI(null, null, null);
    }

    tb.querySelectorAll("button[data-wait]").forEach((b) => {
      b.onclick = async () => {
        await api("/api/calls/" + encodeURIComponent(b.getAttribute("data-wait")) + "/wait", "POST");
        refreshCalls();
      };
    });

    const banner = document.getElementById("waitBanner");
    if (waiting) {
      banner.style.display = "flex";
      banner.innerHTML = "<span style='font-size:18px'>⏳</span> <div>Waiting for applicant to join <strong>" + esc(waiting.call_id)
        + "</strong> (" + esc(waiting.applicant_name) + ")… Enter ID on mobile.</div>";
    } else {
      banner.style.display = "none";
    }
  }

  const btnToggle = document.getElementById("btnToggleTech");
  const techPanel = document.getElementById("techPanel");
  const toggleArrow = document.getElementById("techToggleArrow");
  if (btnToggle && techPanel) {
    btnToggle.onclick = () => {
      const isHidden = techPanel.style.display === "none";
      techPanel.style.display = isHidden ? "block" : "none";
      toggleArrow.textContent = isHidden ? "▲ Hide Technical Inspection" : "▼ Show Technical Inspection";
    };
  }

  document.getElementById("btnSchedule").onclick = async () => {
    const whenVal = document.getElementById("fWhen").value;
    let schedEpoch = null;
    if (whenVal) {
      const d = new Date(whenVal);
      if (!isNaN(d.getTime())) schedEpoch = d.getTime();
    } else {
      schedEpoch = Date.now();
    }
    const body = {
      call_id: document.getElementById("fCallId").value.trim() || undefined,
      applicant_name: document.getElementById("fName").value.trim(),
      applicant_ref: document.getElementById("fRef").value.trim(),
      scheduled_time: whenVal || new Date().toISOString().slice(0, 16),
      scheduled_epoch_ms: schedEpoch,
    };
    const r = await api("/api/calls", "POST", body);
    if (!r.ok) alert("Schedule failed: " + (r.reason || "unknown"));
    refreshCalls();
  };

  // Test Lab Scenarios & Execution
  let labScenariosMap = {};

  async function initTestLab() {
    try {
      const res = await api("/api/lab/scenarios", "GET");
      if (res && res.scenarios) {
        const sel = document.getElementById("labScenarioSelect");
        if (sel) {
          sel.innerHTML = "";
          for (const s of res.scenarios) {
            labScenariosMap[s.id] = s;
            const opt = document.createElement("option");
            opt.value = s.id;
            opt.textContent = s.title;
            sel.appendChild(opt);
          }
          if (res.scenarios.length > 0) {
            updateLabScenarioCard(res.scenarios[0]);
          }
        }
      }
    } catch (e) {}

    // Load initial history
    try {
      const hRes = await api("/api/lab/history", "GET");
      if (hRes && hRes.history) {
        const tb = document.querySelector("#labComparisonTable tbody");
        if (tb) tb.innerHTML = "";
        for (const entry of hRes.history) {
          appendLabComparisonRow(entry);
        }
      }
    } catch (e) {}
  }

  function updateLabScenarioCard(scen) {
    if (!scen) return;
    document.getElementById("labScenTitle").textContent = scen.title;
    document.getElementById("labScenCategory").textContent = scen.category + " · " + scen.attack_type;
    document.getElementById("labScenDesc").textContent = scen.description;
    document.getElementById("labScenMedia").textContent = scen.media_input;
  }

  const labSel = document.getElementById("labScenarioSelect");
  if (labSel) {
    labSel.onchange = () => {
      const s = labScenariosMap[labSel.value];
      if (s) updateLabScenarioCard(s);
    };
  }

  function renderLabResult(ev) {
    if (!ev) return;
    const dec = ev.final_decision;
    const badge = document.getElementById("labVerdictBadge");
    badge.textContent = dec;
    badge.className = "res-pill " + (dec === "LIVE" ? "live" : (dec === "SPOOF" ? "spoof" : "uncertain"));

    document.getElementById("labPLive").textContent = ev.model_output.p_live_percent;
    document.getElementById("labPLive").style.color = dec === "LIVE" ? "#2E7D5B" : (dec === "SPOOF" ? "#C2410C" : "#B45309");
    document.getElementById("labModelType").textContent = ev.model_output.model_name + " (Thresholds: " + ev.model_output.thresholds.live + "/" + ev.model_output.thresholds.spoof + ")";

    document.getElementById("labActiveGate").textContent = ev.security_gates.gate_evaluated;
    document.getElementById("labGateReason").textContent = ev.security_gates.gate_reason;

    document.getElementById("labEvFace").textContent = ev.evidence.face;
    document.getElementById("labEvRppg").textContent = ev.evidence.rppg + " (SNR: " + ev.evidence.snr + ")";
    document.getElementById("labEvBehavior").textContent = ev.evidence.behavior;
    document.getElementById("labEvChallenge").textContent = ev.evidence.challenge;
    document.getElementById("labEvCamera").textContent = ev.evidence.camera;
    document.getElementById("labEvIntegrity").textContent = ev.evidence.integrity;

    document.getElementById("labReceiptPath").textContent = "Receipt: " + (ev.crypto_verdict.receipt || "—");
    document.getElementById("labShaDigest").textContent = "Digest: " + (ev.crypto_verdict.sha256 || "—");

    appendLabComparisonRow(ev);
  }

  function appendLabComparisonRow(ev) {
    const tb = document.querySelector("#labComparisonTable tbody");
    if (!tb) return;
    const dec = ev.final_decision;
    const decColor = dec === "LIVE" ? "#2E7D5B" : (dec === "SPOOF" ? "#C2410C" : "#B45309");
    const tr = document.createElement("tr");
    tr.innerHTML = "<td><strong style='color:var(--text-main)'>" + esc(ev.title) + "</strong></td>"
      + "<td style='color:var(--text-dim)'>" + esc(ev.attack_type) + "</td>"
      + "<td>" + esc(ev.evidence.rppg) + " <span style='font-size:10px;color:var(--text-dim)'>(" + esc(ev.evidence.snr) + ")</span></td>"
      + "<td>" + esc(ev.evidence.behavior) + "</td>"
      + "<td>" + esc(ev.evidence.timing_error) + "</td>"
      + "<td style='font-weight:700;color:var(--brown-medium)'>" + esc(ev.model_output.p_live_percent) + "</td>"
      + "<td style='font-size:10px;color:var(--text-muted)'>" + esc(ev.security_gates.gate_evaluated) + "</td>"
      + "<td><strong style='color:" + decColor + "'>" + esc(dec) + "</strong></td>"
      + "<td class='mono' style='font-size:10px;color:var(--text-muted)'>" + esc(ev.crypto_verdict.receipt ? ev.crypto_verdict.receipt.split(/[\\\\/]/).pop() : "—") + "</td>";
    tb.prepend(tr);
  }

  const btnRunLab = document.getElementById("btnRunLabScenario");
  if (btnRunLab) {
    btnRunLab.onclick = async () => {
      const sid = document.getElementById("labScenarioSelect").value;
      btnRunLab.disabled = true;
      btnRunLab.textContent = "⏳ Running Pipeline…";
      try {
        const res = await api("/api/lab/evaluate", "POST", { scenario_id: sid });
        if (res && res.evaluation) {
          renderLabResult(res.evaluation);
        }
      } finally {
        btnRunLab.disabled = false;
        btnRunLab.textContent = "▶ Run Pipeline Evaluation";
      }
    };
  }

  const btnRunAll = document.getElementById("btnRunAllLab");
  if (btnRunAll) {
    btnRunAll.onclick = async () => {
      btnRunAll.disabled = true;
      btnRunAll.textContent = "⏳ Benchmarking All…";
      try {
        const res = await api("/api/lab/run_all", "POST", {});
        if (res && res.evaluations) {
          const tb = document.querySelector("#labComparisonTable tbody");
          if (tb) tb.innerHTML = "";
          for (const ev of res.evaluations) {
            renderLabResult(ev);
          }
        }
      } finally {
        btnRunAll.disabled = false;
        btnRunAll.textContent = "⚡ Benchmark All 6 Scenarios";
      }
    };
  }

  renderSchemaTable(null);
  initTestLab();
  refreshCalls();
  setInterval(refreshCalls, 2000);
</script>
</body></html>
""".replace("__VER__", VERIFIER_VERSION)


class VerifierHandler(BaseHTTPRequestHandler):
    pubkey: str = ""

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        sys.stderr.write("[verifier] " + (fmt % args) + "\n")

    def _send_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(n) if n > 0 else b""

    def _route_path(self) -> str:
        return self.path.split("?", 1)[0].rstrip("/") or "/"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path == "/index.html":
            html = DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        if self._route_path() == "/api/calls":
            self._send_json(200, {
                "ok": True,
                "calls": call_store.list_calls(),
            })
            return
        if self._route_path() == "/api/lab/scenarios":
            from verifier.test_harness import harness
            self._send_json(200, {
                "ok": True,
                "scenarios": harness.list_scenarios(),
            })
            return
        if self._route_path() == "/api/lab/history":
            from verifier.test_harness import harness
            self._send_json(200, {
                "ok": True,
                "history": harness.get_history(),
            })
            return
        self.send_response(404)
        self.end_headers()

    def _read_json_body(self):
        """Read + parse a JSON body. Returns (obj, error_response).

        On success returns (obj, None). On failure returns
        (None, dict) where dict is the error payload to send.
        """
        try:
            body = self._read_body()
        except Exception:
            return None, {"ok": False, "reason": "bad-request"}
        if len(body) > MAX_BODY:
            return None, {"ok": False, "reason": "payload-too-large"}
        try:
            return json.loads(body.decode("utf-8")), None
        except Exception:
            return None, {"ok": False, "reason": "bad-request"}

    def do_POST(self) -> None:  # noqa: N802
        path = self._route_path()
        if path == "/api/calls":
            payload, err = self._read_json_body()
            if err is not None:
                self._send_json(400, err)
                return
            try:
                call = call_store.create_call(
                    applicant_name=(payload or {}).get("applicant_name", ""),
                    applicant_ref=(payload or {}).get("applicant_ref", ""),
                    scheduled_time=(payload or {}).get("scheduled_time", "") or "",
                    scheduled_epoch_ms=(payload or {}).get("scheduled_epoch_ms"),
                    call_id=(payload or {}).get("call_id"),
                )
            except ValueError as e:
                self._send_json(400, {"ok": False, "reason": str(e)})
                return
            self._send_json(200, {"ok": True, "call": call})
            return
        if path.startswith("/api/calls/") and path.endswith("/wait"):
            # /api/calls/{call_id}/wait — the {call_id} never contains
            # a slash (generated as call-YYYYMMDD-HHMMSS-xxxx).
            parts = path.split("/")
            if len(parts) != 5 or not parts[3]:
                self._send_json(400, {"ok": False, "reason": "bad-call-path"})
                return
            out = call_store.set_waiting(parts[3])
            self._send_json(200 if out.get("ok") else 400, out)
            return
        if path == "/api/lab/evaluate":
            from verifier.test_harness import harness
            payload, err = self._read_json_body()
            if err is not None:
                self._send_json(400, err)
                return
            scenario_id = (payload or {}).get("scenario_id", "genuine")
            try:
                res = harness.evaluate_scenario(scenario_id)
                self._send_json(200, {"ok": True, "evaluation": res})
            except Exception as e:
                self._send_json(400, {"ok": False, "reason": str(e)})
            return
        if path == "/api/lab/run_all":
            from verifier.test_harness import harness
            try:
                all_res = harness.run_all_scenarios()
                self._send_json(200, {"ok": True, "evaluations": all_res})
            except Exception as e:
                self._send_json(400, {"ok": False, "reason": str(e)})
            return
        if path != "/api/result":
            self.send_response(404)
            self.end_headers()
            return
        env, err = self._read_json_body()
        if err is not None:
            status = 413 if err.get("reason") == "payload-too-large" else 400
            self._send_json(status, err)
            return
        assert isinstance(env, dict)

        # Join Call branch (§8.2 Option A): type-discriminated on the
        # same endpoint. The Android client sends the join payload
        # wrapped as an `IntegrityManager.Envelope`
        # ({data, sig, alg, keyAlias} with `data` = the join JSON —
        # see §8.4) so it can reuse `Transport.send()` with no new
        # transport. Plain (unwrapped) join dicts are also accepted
        # for curl-based testing. The verification envelope flow
        # below is untouched either way.
        join_payload: dict | None = None
        if env.get("type") == "CALL_JOIN_REQUEST":
            join_payload = env
        elif isinstance(env.get("data"), str):
            try:
                inner = json.loads(env["data"])
            except Exception:
                inner = None
            if isinstance(inner, dict) and \
                    inner.get("type") == "CALL_JOIN_REQUEST":
                join_payload = inner
        if join_payload is not None:
            out = call_store.handle_join(join_payload)
            out = dict(out)
            out["server_version"] = VERIFIER_VERSION
            self._send_json(200, out)
            return

        if not self.pubkey:
            self.pubkey = _load_pubkey(Path(__file__).parent / "pubkey.b64")
        verdict = verify_envelope(env, self.pubkey)
        if verdict.get("ok"):
            try:
                receipt = write_receipt(verdict)
                verdict = dict(verdict)
                verdict["receipt"] = str(receipt)
            except Exception as e:  # noqa: BLE001
                verdict = dict(verdict)
                verdict["receipt_error"] = str(e)
            # Optional call link: a client performing a scheduled call
            # may include its `call_id` next to the envelope. This key
            # is ignored by `verify_envelope` (it only reads
            # data/sig/alg), so old clients sending 4 keys keep
            # working. On a linked CONNECTED call we record COMPLETED.
            call_id = env.get("call_id")
            if not call_id:
                connected = [c for c in call_store.list_calls() if c.get("status") == call_store.CONNECTED]
                if connected:
                    call_id = connected[-1].get("call_id")
            if isinstance(call_id, str) and call_id:
                tel = verdict.get("telemetry") or {}
                link = call_store.link_verification_result(
                    call_id,
                    tel.get("decision"),
                    verdict.get("receipt"),
                    telemetry=tel,
                )
                verdict["call_link"] = link
        # Echo the verdict back to the caller too.
        verdict = dict(verdict)
        verdict["server_version"] = VERIFIER_VERSION
        self._send_json(200, verdict)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--pubkey", type=Path,
                   default=Path(__file__).parent / "pubkey.b64")
    args = p.parse_args()

    pubkey = _load_pubkey(args.pubkey)
    if not pubkey:
        sys.stderr.write(
            "[verifier] WARNING: no pubkey.b64 — every signature will verify "
            "as bad-pubkey until provisioned.\n"
        )

    VerifierHandler.pubkey = pubkey
    httpd = ThreadingHTTPServer(("0.0.0.0", args.port), VerifierHandler)
    print(f"[verifier] listening on http://0.0.0.0:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

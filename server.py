"""
Rally Controls Live Times – web server for the Rally Control Timer app.

Itinerary = ordered time controls (TC0, TC1, …) with target minutes between them.
Penalties are calculated from live times:
  - Late:  10 seconds per full minute late
  - Early: 1 minute per full minute early
"""
from __future__ import annotations

from flask import Flask, request, jsonify
import os
import re
from datetime import datetime, timedelta

app = Flask(__name__, static_folder=None)


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


entries = []
_next_entry_id = 0

penalties = []
_next_penalty_id = 0

# Ordered time-control program. First item is the rally start (usually TC0).
# Each item: controlType (TC|SS), number, code (e.g. TC01), targetMinutesFromPrev,
# checkPenalties (bool) — if False, no auto penalty for arrival at this control.
itinerary = []
_next_itinerary_id = 0


# ---------- Time / penalty helpers ----------

def normalize_tc(tc) -> str:
    return str(tc or "").strip()


def build_control_code(control_type, number) -> str:
    """Build live-times TC label from type + number, e.g. TC + 01 → TC01."""
    kind = str(control_type or "TC").strip().upper()
    if kind not in ("TC", "SS"):
        kind = "TC"
    num = str(number or "").strip().upper().replace(" ", "")
    # Allow values already prefixed (TC01 / SS1)
    if num.startswith("TC") or num.startswith("SS"):
        return num
    return f"{kind}{num}"


def parse_bool(value, default=True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def itinerary_item_from_payload(data: dict, *, is_first: bool) -> dict:
    control_type = str(data.get("controlType") or data.get("type") or "TC").strip().upper()
    if control_type not in ("TC", "SS"):
        control_type = "TC"
    number = str(data.get("number") or "").strip()
    # Back-compat: allow legacy "code" only
    code = normalize_tc(data.get("code"))
    if number:
        code = build_control_code(control_type, number)
    elif code:
        upper = code.upper()
        if upper.startswith("SS"):
            control_type = "SS"
            number = code[2:]
        elif upper.startswith("TC"):
            control_type = "TC"
            number = code[2:]
        else:
            number = code
            code = build_control_code(control_type, number)
    try:
        mins = int(data.get("targetMinutesFromPrev", 0))
    except (TypeError, ValueError):
        mins = 0
    if mins < 0:
        mins = 0
    if is_first:
        mins = 0
    check = parse_bool(data.get("checkPenalties"), default=True)
    if is_first:
        # Start control has no inbound leg; keep flag but it is unused until moved.
        pass
    return {
        "controlType": control_type,
        "number": number,
        "code": code,
        "name": str(data.get("name") or ""),
        "targetMinutesFromPrev": mins,
        "checkPenalties": check,
    }


def parse_clock(time_str: str):
    """Parse HH:MM:SS or HH:MM:SS.xx into a datetime on a fixed reference day."""
    if not time_str:
        return None
    s = str(time_str).strip()
    # Allow optional date prefix "YYYY-MM-DD HH:MM:SS..."
    if " " in s and re.match(r"^\d{4}-\d{2}-\d{2}\s", s):
        s = s.split(" ", 1)[1]
    s = s.replace(",", ".")
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt)
            return datetime(2000, 1, 1, t.hour, t.minute, t.second, t.microsecond)
        except ValueError:
            continue
    return None


def format_clock(dt: datetime) -> str:
    if dt.microsecond:
        # hundredths
        hundredths = dt.microsecond // 10000
        return f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}.{hundredths:02d}"
    return f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def format_penalty_duration(total_seconds: int) -> str:
    if total_seconds < 0:
        total_seconds = 0
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"+{hours}:{minutes:02d}:{seconds:02d}"
    return f"+{minutes}:{seconds:02d}"


def official_time_for_car_tc(car_number: int, tc_code: str):
    """Earliest recorded time for this car at this TC (case-insensitive TC match)."""
    want = normalize_tc(tc_code).lower()
    times = []
    for e in entries:
        if int(e.get("carNumber", -1)) != int(car_number):
            continue
        if normalize_tc(e.get("tc")).lower() != want:
            continue
        dt = parse_clock(e.get("time", ""))
        if dt is not None:
            times.append(dt)
    if not times:
        return None
    return min(times)


def compute_leg_penalty(prev_time: datetime, actual_time: datetime, target_minutes: int):
    """
    Returns dict with delta details, or None if on time (less than 1 full minute early/late).
    Late  : 10 seconds penalty per full minute late
    Early : 1 minute penalty per full minute early
    """
    target_arrival = prev_time + timedelta(minutes=int(target_minutes))
    # Handle simple overnight wrap if actual looks earlier but was next day
    actual = actual_time
    if actual + timedelta(hours=12) < target_arrival:
        actual = actual + timedelta(days=1)
    delta = actual - target_arrival
    delta_seconds = int(delta.total_seconds())
    if delta_seconds >= 60:
        minutes_late = delta_seconds // 60
        penalty_seconds = minutes_late * 10
        return {
            "kind": "late",
            "minutes": minutes_late,
            "penaltySeconds": penalty_seconds,
            "penalty": format_penalty_duration(penalty_seconds),
            "targetTime": format_clock(target_arrival),
            "actualTime": format_clock(actual_time),
            "reason": f"Late {minutes_late} min at control (10s per min)",
        }
    if delta_seconds <= -60:
        minutes_early = (-delta_seconds) // 60
        penalty_seconds = minutes_early * 60
        return {
            "kind": "early",
            "minutes": minutes_early,
            "penaltySeconds": penalty_seconds,
            "penalty": format_penalty_duration(penalty_seconds),
            "targetTime": format_clock(target_arrival),
            "actualTime": format_clock(actual_time),
            "reason": f"Early {minutes_early} min at control (1 min per min)",
        }
    return {
        "kind": "ok",
        "minutes": 0,
        "penaltySeconds": 0,
        "penalty": "+0:00",
        "targetTime": format_clock(target_arrival),
        "actualTime": format_clock(actual_time),
        "reason": "On time",
    }


def recalculate_auto_penalties():
    """
    Rebuild automatic itinerary penalties from live times + itinerary.
    Manual penalties (source != 'auto') are kept.
    """
    global penalties, _next_penalty_id
    manual = [p for p in penalties if p.get("source") != "auto"]
    auto = []

    if len(itinerary) < 2:
        penalties = manual
        return {"ok": True, "autoCount": 0, "checked": 0, "message": "Need at least 2 controls in itinerary"}

    checked = 0
    # Collect cars that appear in live times
    cars = sorted({int(e.get("carNumber", 0)) for e in entries})

    for i in range(1, len(itinerary)):
        prev = itinerary[i - 1]
        curr = itinerary[i]
        prev_code = normalize_tc(prev.get("code"))
        curr_code = normalize_tc(curr.get("code"))
        try:
            target_minutes = int(curr.get("targetMinutesFromPrev") or 0)
        except (TypeError, ValueError):
            target_minutes = 0
        if not prev_code or not curr_code or target_minutes < 0:
            continue
        # If this control is marked "no", skip penalty checks for arrivals here.
        if not parse_bool(curr.get("checkPenalties"), default=True):
            continue

        for car in cars:
            prev_t = official_time_for_car_tc(car, prev_code)
            curr_t = official_time_for_car_tc(car, curr_code)
            if prev_t is None or curr_t is None:
                continue
            checked += 1
            result = compute_leg_penalty(prev_t, curr_t, target_minutes)
            if result is None or result["kind"] == "ok":
                continue
            auto.append({
                "id": _next_penalty_id,
                "carNumber": car,
                "penalty": result["penalty"],
                "tc": curr_code,
                "reason": result["reason"],
                "kind": result["kind"],
                "source": "auto",
                "fromTc": prev_code,
                "targetTime": result["targetTime"],
                "actualTime": result["actualTime"],
                "targetMinutes": target_minutes,
            })
            _next_penalty_id += 1

    penalties = manual + auto
    return {"ok": True, "autoCount": len(auto), "checked": checked}


@app.route("/")
def index():
    return r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rally Controls Live Times</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; background: #1a1a1a; color: #ffb74d; margin: 0; padding: 24px; }
    h1 { font-size: 1.5rem; margin-bottom: 16px; }
    .tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; border-bottom: 1px solid #333; padding-bottom: 0; }
    .tab {
      background: transparent; color: #888; border: none; border-bottom: 3px solid transparent;
      padding: 10px 16px; font-size: 14px; font-weight: 700; letter-spacing: 0.06em;
      cursor: pointer; margin-bottom: -1px;
    }
    .tab:hover { color: #ffb74d; }
    .tab.active { color: #ffb74d; border-bottom-color: #ffb74d; }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .entry { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #333; font-size: 1.25rem; gap: 8px; }
    .entry .num-car { color: #ccc; }
    .entry .time { font-variant-numeric: tabular-nums; color: #ffb74d; }
    .entry-actions { display: flex; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }
    .entry-actions button, table.data button { padding: 4px 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }
    .edit-btn { background: #555; color: #ffb74d; }
    .delete-btn { background: #c62828; color: #fff; }
    .move-btn { background: #333; color: #ffb74d; }
    .entry-actions .move-tc-select { padding: 4px 6px; background: #2a2a2a; color: #ffb74d; border: 1px solid #444; border-radius: 4px; font-size: 12px; cursor: pointer; min-width: 72px; }
    .empty { color: #666; padding: 24px 0; }
    .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; }
    .modal { background: #2a2a2a; padding: 20px; border-radius: 8px; min-width: 280px; max-width: 92vw; }
    .modal label { display: block; color: #aaa; font-size: 12px; margin-top: 10px; margin-bottom: 4px; }
    .modal input, .modal select, .modal textarea {
      width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px;
      color: #fff; font-size: 14px; box-sizing: border-box; font-family: inherit;
    }
    .modal-btns { margin-top: 16px; display: flex; gap: 8px; justify-content: flex-end; }
    .modal-btns button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
    .modal-btns .save-btn { background: #ffb74d; color: #1a1a1a; }
    .modal-btns .cancel-btn { background: #555; color: #fff; }
    #list, #penaltyList, #itineraryList, #schedulePreview { max-width: 920px; }
    .tc-block { margin-bottom: 24px; }
    .tc-title { font-size: 1.1rem; color: #ffb74d; margin: 0 0 8px 0; padding-bottom: 4px; border-bottom: 1px solid #444; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
    .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
    .btn-danger { background: #c62828; color: #fff; }
    .btn-primary { background: #ffb74d; color: #1a1a1a; font-weight: 700; }
    .btn-secondary { background: #444; color: #ffb74d; }
    .hint { color: #888; font-size: 14px; margin: 0 0 12px 0; line-height: 1.45; }
    .meta { color: #666; font-size: 12px; margin: 0 0 12px 0; }
    .rules {
      background: #222; border: 1px solid #333; border-radius: 8px; padding: 12px 14px;
      color: #ccc; font-size: 13px; margin-bottom: 14px; max-width: 920px; line-height: 1.5;
    }
    .rules strong { color: #ffb74d; }
    table.data { width: 100%; border-collapse: collapse; }
    table.data th, table.data td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #333; vertical-align: top; }
    table.data th { color: #aaa; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
    table.data td { color: #ffb74d; font-size: 15px; }
    table.data td.muted { color: #ccc; }
    table.data td.actions { white-space: nowrap; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
    .badge-late { background: #c62828; color: #fff; }
    .badge-early { background: #ef6c00; color: #fff; }
    .badge-auto { background: #333; color: #ffb74d; }
    .badge-manual { background: #333; color: #aaa; }
    .badge-ok { background: #2e7d32; color: #fff; }
    .badge-skip { background: #555; color: #ddd; }
    .live-tcs { color: #888; font-size: 12px; margin-bottom: 12px; }
    .row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  </style>
</head>
<body>
  <h1>Rally Controls Live Times</h1>

  <nav class="tabs" role="tablist" aria-label="Main sections">
    <button type="button" class="tab active" role="tab" aria-selected="true" data-tab="times">LIVE TIMES</button>
    <button type="button" class="tab" role="tab" aria-selected="false" data-tab="penalties">PENALTY LIST</button>
    <button type="button" class="tab" role="tab" aria-selected="false" data-tab="itinerary">ITINERARY</button>
  </nav>

  <!-- LIVE TIMES -->
  <section id="panel-times" class="tab-panel active" role="tabpanel">
    <div class="toolbar">
      <button type="button" class="btn btn-danger" id="resetBtn">Reset all times</button>
    </div>
    <p class="hint">Auto-refreshing every 3 seconds. Split by TC. Oldest first.</p>
    <p style="margin:12px 0 4px 0;">
      <label for="tcFilter" style="color:#aaa;font-size:14px;">Show entries: </label>
      <select id="tcFilter" style="padding:6px 10px;background:#2a2a2a;color:#ffb74d;border:1px solid #444;border-radius:6px;font-size:14px;min-width:140px;">
        <option value="__all__">All TCs</option>
      </select>
    </p>
    <p id="lastUpdate" class="meta">Last updated: --</p>
    <div id="list">
      <div class="empty">No entries yet. Record a time on the app to see it here.</div>
    </div>
  </section>

  <!-- PENALTY LIST -->
  <section id="panel-penalties" class="tab-panel" role="tabpanel" hidden>
    <div class="toolbar">
      <button type="button" class="btn btn-primary" id="addPenaltyBtn">Add penalty</button>
      <button type="button" class="btn btn-secondary" id="recalcPenaltiesBtn">Recalculate from itinerary</button>
      <button type="button" class="btn btn-danger" id="resetPenaltiesBtn">Clear auto penalties</button>
    </div>
    <div class="rules">
      <strong>Auto rules:</strong> Late = <strong>10 seconds</strong> per full minute late.
      Early = <strong>1 minute</strong> per full minute early.
      Manual penalties are kept when recalculating.
    </div>
    <p id="penaltyStatus" class="meta"></p>
    <div id="penaltyList">
      <div class="empty">No penalties yet.</div>
    </div>
  </section>

  <!-- ITINERARY -->
  <section id="panel-itinerary" class="tab-panel" role="tabpanel" hidden>
    <div class="toolbar">
      <button type="button" class="btn btn-primary" id="addItineraryBtn">Add time control</button>
      <button type="button" class="btn btn-secondary" id="recalcFromItineraryBtn">Recalculate penalties</button>
      <button type="button" class="btn btn-danger" id="resetItineraryBtn">Clear itinerary</button>
    </div>
    <div class="rules">
      Add controls in order. Choose <strong>TC</strong> or <strong>SS</strong>, then the
      <strong>number</strong> (e.g. TC + 01 → <strong>TC01</strong>, SS + 1 → <strong>SS1</strong>).
      Set <strong>target minutes from previous</strong> (not needed for the first/start control).
      <strong>Check penalties?</strong> Yes = early/late rules apply at this control;
      No = times are still shown in schedule check, but <em>no auto penalty</em> is created.
      Labels must match Live Times names.
    </div>
    <p id="liveTcHints" class="live-tcs"></p>
    <div id="itineraryList">
      <div class="empty">No itinerary yet. Add TC0 (start), then TC1 with target minutes.</div>
    </div>
    <h2 style="margin-top:28px;font-size:1.1rem;">Schedule check (from live times)</h2>
    <p class="hint">Shows target vs actual for each car between consecutive itinerary controls.</p>
    <div id="schedulePreview"><div class="empty">Set itinerary and record times to preview.</div></div>
  </section>

  <script>
    function escapeHtml(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }

    function showTab(name) {
      document.querySelectorAll('.tab').forEach(function(btn) {
        var on = btn.getAttribute('data-tab') === name;
        btn.classList.toggle('active', on);
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      document.querySelectorAll('.tab-panel').forEach(function(panel) {
        var on = panel.id === 'panel-' + name;
        panel.classList.toggle('active', on);
        if (on) panel.removeAttribute('hidden');
        else panel.setAttribute('hidden', '');
      });
      if (name === 'penalties') refreshPenalties();
      if (name === 'itinerary') { refreshItinerary(); refreshSchedulePreview(); refreshLiveTcHints(); }
    }
    document.querySelectorAll('.tab').forEach(function(btn) {
      btn.addEventListener('click', function() { showTab(btn.getAttribute('data-tab')); });
    });

    /* ---------- Live times ---------- */
    var lastData = [];
    function refresh() {
      fetch('/entries?t=' + Date.now())
        .then(r => r.json())
        .then(data => {
          lastData = data;
          document.getElementById('lastUpdate').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
          var tcFilter = document.getElementById('tcFilter');
          if (data.length === 0) {
            document.getElementById('list').innerHTML = '<div class="empty">No entries yet. Record a time on the app to see it here.</div>';
            tcFilter.innerHTML = '<option value="__all__">All TCs</option>';
            return;
          }
          function displayTc(tcVal) {
            if (tcVal == null || tcVal === '') return '(No TC)';
            return String(tcVal).trim();
          }
          var byTc = {};
          data.forEach(function(e) {
            var key = (e.tc != null && e.tc !== '') ? String(e.tc).trim() : '';
            if (!byTc[key]) byTc[key] = [];
            byTc[key].push(e);
          });
          var tcs = Object.keys(byTc).sort();
          var currentFilter = tcFilter.value;
          tcFilter.innerHTML = '<option value="__all__">All TCs</option>' + tcs.map(function(tcKey) {
            return '<option value="' + escapeHtml(tcKey) + '">' + escapeHtml(displayTc(tcKey)) + '</option>';
          }).join('');
          if (currentFilter !== '__all__' && tcs.indexOf(currentFilter) >= 0) tcFilter.value = currentFilter;
          else tcFilter.value = '__all__';
          renderList(data, tcFilter.value);
          if (document.getElementById('panel-itinerary').classList.contains('active')) {
            refreshLiveTcHints();
            refreshSchedulePreview();
          }
        })
        .catch(function() { document.getElementById('lastUpdate').textContent = 'Last updated: (error)'; });
    }
    function renderList(data, filterTc) {
      var list = document.getElementById('list');
      var tcFilter = document.getElementById('tcFilter');
      if (data.length === 0) {
        list.innerHTML = '<div class="empty">No entries yet. Record a time on the app to see it here.</div>';
        return;
      }
      function displayTc(tcVal) {
        if (tcVal == null || tcVal === '') return '(No TC)';
        return String(tcVal).trim();
      }
      var byTc = {};
      data.forEach(function(e) {
        var key = (e.tc != null && e.tc !== '') ? String(e.tc).trim() : '';
        if (!byTc[key]) byTc[key] = [];
        byTc[key].push(e);
      });
      var tcs = Object.keys(byTc).sort();
      if (filterTc === undefined) filterTc = tcFilter.value;
      var tcsToShow = (filterTc === '__all__' || filterTc === undefined) ? tcs : [filterTc];
      list.innerHTML = tcsToShow.map(function(tcKey) {
        var rows = byTc[tcKey].slice().reverse().map(function(e, i) {
          var id = e.id != null ? e.id : i;
          var currentTc = (e.tc != null && e.tc !== '') ? String(e.tc).trim() : '';
          var moveOpts = tcs.map(function(tcOpt) {
            var sel = tcOpt === currentTc ? ' selected' : '';
            return '<option value="' + escapeHtml(tcOpt) + '"' + sel + '>' + escapeHtml(displayTc(tcOpt)) + '</option>';
          }).join('');
          return '<div class="entry" data-id="' + id + '"><span class="num-car">' + (i+1) + '. #' + escapeHtml(String(e.carNumber)) + '</span><span class="time">' + escapeHtml(e.time) + '</span><div class="entry-actions"><select class="move-tc-select" data-id="' + id + '" title="Move to TC">' + moveOpts + '</select><button type="button" class="edit-btn" data-id="' + id + '">Edit</button><button type="button" class="delete-btn" data-id="' + id + '">Delete</button></div></div>';
        }).join('');
        return '<div class="tc-block"><h2 class="tc-title">' + escapeHtml(displayTc(tcKey)) + '</h2>' + rows + '</div>';
      }).join('');
    }
    function findEntryById(id) {
      var n = parseInt(id, 10);
      if (isNaN(n)) return null;
      for (var i = 0; i < lastData.length; i++) {
        if (lastData[i].id === n || lastData[i].id == id) return lastData[i];
      }
      return null;
    }
    function showEditModal(entry) {
      var overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      var timeVal = entry.time || '';
      var carVal = String(entry.carNumber != null ? entry.carNumber : '');
      overlay.innerHTML = '<div class="modal"><h3 style="margin:0 0 12px 0;color:#ffb74d;">Edit entry</h3><label>Car number</label><input type="number" id="editCar" min="0" max="99" value="' + escapeHtml(carVal) + '"><label>Time (e.g. 00:01:23.45)</label><input type="text" id="editTime" value="' + escapeHtml(timeVal) + '"><div class="modal-btns"><button type="button" class="cancel-btn">Cancel</button><button type="button" class="save-btn">Save</button></div></div>';
      document.body.appendChild(overlay);
      overlay.querySelector('.cancel-btn').onclick = function() { document.body.removeChild(overlay); };
      overlay.querySelector('.save-btn').onclick = function() {
        var car = parseInt(overlay.querySelector('#editCar').value, 10);
        if (isNaN(car) || car < 0 || car > 99) { alert('Car number must be 0–99'); return; }
        var time = overlay.querySelector('#editTime').value.trim();
        fetch('/entry/' + entry.id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ carNumber: car, time: time }) })
          .then(function(r) { if (r.ok) { document.body.removeChild(overlay); refresh(); } else { alert('Update failed'); } })
          .catch(function() { alert('Update failed'); });
      };
      overlay.onclick = function(ev) { if (ev.target === overlay) document.body.removeChild(overlay); };
    }
    document.getElementById('list').addEventListener('click', function(ev) {
      var btn = ev.target.closest('.edit-btn');
      if (btn) { var entry = findEntryById(btn.getAttribute('data-id')); if (entry) showEditModal(entry); return; }
      btn = ev.target.closest('.delete-btn');
      if (btn) {
        if (!confirm('Delete this entry?')) return;
        fetch('/entry/' + btn.getAttribute('data-id'), { method: 'DELETE' }).then(function(r) { if (r.ok) refresh(); });
      }
    });
    document.getElementById('list').addEventListener('change', function(ev) {
      var sel = ev.target.closest('.move-tc-select');
      if (!sel) return;
      var entry = findEntryById(sel.getAttribute('data-id'));
      if (!entry) return;
      var newTc = sel.value;
      var currentTc = (entry.tc != null && entry.tc !== '') ? String(entry.tc).trim() : '';
      if (newTc === currentTc) return;
      fetch('/entry/' + entry.id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tc: newTc }) })
        .then(function(r) { if (r.ok) refresh(); else alert('Move failed'); });
    });
    document.getElementById('tcFilter').onchange = function() { renderList(lastData, this.value); };
    document.getElementById('resetBtn').onclick = function() {
      if (!confirm('Are you sure you want to delete all times?')) return;
      fetch('/reset-entries', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
        .then(function(r) { if (r.ok) refresh(); });
    };

    /* ---------- Penalties ---------- */
    var lastPenalties = [];
    function refreshPenalties() {
      fetch('/penalties?t=' + Date.now())
        .then(function(r) { return r.json(); })
        .then(function(data) {
          lastPenalties = data || [];
          renderPenalties();
        })
        .catch(function() {
          document.getElementById('penaltyList').innerHTML = '<div class="empty">Failed to load penalties.</div>';
        });
    }
    function renderPenalties() {
      var el = document.getElementById('penaltyList');
      if (!lastPenalties.length) {
        el.innerHTML = '<div class="empty">No penalties yet. Set the itinerary, then recalculate.</div>';
        return;
      }
      var rows = lastPenalties.map(function(p, i) {
        var kind = p.kind || '';
        var kindBadge = kind === 'late' ? '<span class="badge badge-late">LATE</span>'
          : kind === 'early' ? '<span class="badge badge-early">EARLY</span>' : '';
        var srcBadge = p.source === 'auto'
          ? '<span class="badge badge-auto">AUTO</span>'
          : '<span class="badge badge-manual">MANUAL</span>';
        return '<tr data-id="' + p.id + '">' +
          '<td class="muted">' + (i + 1) + '</td>' +
          '<td>#' + escapeHtml(String(p.carNumber)) + '</td>' +
          '<td>' + escapeHtml(p.penalty || '') + '</td>' +
          '<td class="muted">' + escapeHtml(p.tc || '') + '</td>' +
          '<td class="muted">' + escapeHtml(p.reason || '') + '</td>' +
          '<td>' + kindBadge + ' ' + srcBadge + '</td>' +
          '<td class="actions">' +
            (p.source === 'auto' ? '' : '<button type="button" class="edit-btn pen-edit" data-id="' + p.id + '">Edit</button> ') +
            '<button type="button" class="delete-btn pen-del" data-id="' + p.id + '">Delete</button></td>' +
          '</tr>';
      }).join('');
      el.innerHTML = '<table class="data"><thead><tr><th>#</th><th>Car</th><th>Penalty</th><th>TC</th><th>Reason</th><th>Type</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>';
    }
    function findPenalty(id) {
      var n = parseInt(id, 10);
      for (var i = 0; i < lastPenalties.length; i++) {
        if (lastPenalties[i].id === n || lastPenalties[i].id == id) return lastPenalties[i];
      }
      return null;
    }
    function showPenaltyModal(existing) {
      var overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      var p = existing || { carNumber: '', penalty: '', tc: '', reason: '' };
      overlay.innerHTML =
        '<div class="modal"><h3 style="margin:0 0 12px 0;color:#ffb74d;">' + (existing ? 'Edit penalty' : 'Add penalty') + '</h3>' +
        '<label>Car number</label><input type="number" id="penCar" min="0" max="99" value="' + escapeHtml(String(p.carNumber != null ? p.carNumber : '')) + '">' +
        '<label>Penalty (e.g. +0:10 or +1:00)</label><input type="text" id="penVal" value="' + escapeHtml(p.penalty || '') + '">' +
        '<label>TC / Stage</label><input type="text" id="penTc" value="' + escapeHtml(p.tc || '') + '">' +
        '<label>Reason</label><input type="text" id="penReason" value="' + escapeHtml(p.reason || '') + '">' +
        '<div class="modal-btns"><button type="button" class="cancel-btn">Cancel</button><button type="button" class="save-btn">Save</button></div></div>';
      document.body.appendChild(overlay);
      overlay.querySelector('.cancel-btn').onclick = function() { document.body.removeChild(overlay); };
      overlay.querySelector('.save-btn').onclick = function() {
        var car = parseInt(overlay.querySelector('#penCar').value, 10);
        if (isNaN(car) || car < 0 || car > 99) { alert('Car number must be 0–99'); return; }
        var body = {
          carNumber: car,
          penalty: overlay.querySelector('#penVal').value.trim(),
          tc: overlay.querySelector('#penTc').value.trim(),
          reason: overlay.querySelector('#penReason').value.trim(),
          source: 'manual'
        };
        var req = existing
          ? fetch('/penalties/' + existing.id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
          : fetch('/penalties', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        req.then(function(r) { if (r.ok) { document.body.removeChild(overlay); refreshPenalties(); } else alert('Save failed'); });
      };
      overlay.onclick = function(ev) { if (ev.target === overlay) document.body.removeChild(overlay); };
    }
    function runRecalculate() {
      return fetch('/recalculate-penalties', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(res) {
          var msg = 'Checked ' + (res.checked || 0) + ' car/legs · auto penalties: ' + (res.autoCount || 0);
          if (res.message) msg += ' · ' + res.message;
          var status = document.getElementById('penaltyStatus');
          if (status) status.textContent = msg;
          refreshPenalties();
          refreshSchedulePreview();
          return res;
        });
    }
    document.getElementById('addPenaltyBtn').onclick = function() { showPenaltyModal(null); };
    document.getElementById('recalcPenaltiesBtn').onclick = function() { runRecalculate(); };
    document.getElementById('resetPenaltiesBtn').onclick = function() {
      if (!confirm('Clear automatic penalties? Manual penalties are kept.')) return;
      fetch('/reset-penalties', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ autoOnly: true }) })
        .then(function(r) { if (r.ok) refreshPenalties(); });
    };
    document.getElementById('penaltyList').addEventListener('click', function(ev) {
      var edit = ev.target.closest('.pen-edit');
      if (edit) { var p = findPenalty(edit.getAttribute('data-id')); if (p) showPenaltyModal(p); return; }
      var del = ev.target.closest('.pen-del');
      if (del) {
        if (!confirm('Delete this penalty?')) return;
        fetch('/penalties/' + del.getAttribute('data-id'), { method: 'DELETE' })
          .then(function(r) { if (r.ok) refreshPenalties(); });
      }
    });

    /* ---------- Itinerary ---------- */
    var lastItinerary = [];
    function refreshLiveTcHints() {
      var set = {};
      lastData.forEach(function(e) {
        var t = (e.tc != null && e.tc !== '') ? String(e.tc).trim() : '';
        if (t) set[t] = true;
      });
      var names = Object.keys(set).sort();
      document.getElementById('liveTcHints').textContent = names.length
        ? ('TC names currently in Live Times: ' + names.join(', '))
        : 'No TC names in live times yet.';
    }
    function refreshItinerary() {
      fetch('/itinerary?t=' + Date.now())
        .then(function(r) { return r.json(); })
        .then(function(data) {
          lastItinerary = data || [];
          renderItinerary();
        })
        .catch(function() {
          document.getElementById('itineraryList').innerHTML = '<div class="empty">Failed to load itinerary.</div>';
        });
    }
    function renderItinerary() {
      var el = document.getElementById('itineraryList');
      if (!lastItinerary.length) {
        el.innerHTML = '<div class="empty">No itinerary yet. Add start control (TC or SS + number), then the next with target minutes.</div>';
        return;
      }
      var rows = lastItinerary.map(function(item, i) {
        var type = (item.controlType || (String(item.code || '').toUpperCase().indexOf('SS') === 0 ? 'SS' : 'TC'));
        var num = item.number != null && item.number !== '' ? item.number : String(item.code || '').replace(/^TC|^SS/i, '');
        var targetCell = i === 0
          ? '<span class="muted">Start — no previous target</span>'
          : ('<strong>' + escapeHtml(String(item.targetMinutesFromPrev != null ? item.targetMinutesFromPrev : '')) + ' min</strong> from ' + escapeHtml(lastItinerary[i-1].code || ''));
        var check = item.checkPenalties !== false;
        var checkBadge = i === 0
          ? '<span class="muted">—</span>'
          : (check ? '<span class="badge badge-ok">YES</span>' : '<span class="badge badge-skip">NO</span>');
        return '<tr data-id="' + item.id + '">' +
          '<td class="muted">' + (i + 1) + '</td>' +
          '<td class="muted">' + escapeHtml(type) + '</td>' +
          '<td class="muted">' + escapeHtml(String(num)) + '</td>' +
          '<td><strong>' + escapeHtml(item.code || '') + '</strong></td>' +
          '<td>' + targetCell + '</td>' +
          '<td>' + checkBadge + '</td>' +
          '<td class="actions">' +
            '<button type="button" class="move-btn it-up" data-id="' + item.id + '" title="Move up">↑</button> ' +
            '<button type="button" class="move-btn it-down" data-id="' + item.id + '" title="Move down">↓</button> ' +
            '<button type="button" class="edit-btn it-edit" data-id="' + item.id + '">Edit</button> ' +
            '<button type="button" class="delete-btn it-del" data-id="' + item.id + '">Delete</button>' +
          '</td></tr>';
      }).join('');
      el.innerHTML = '<table class="data"><thead><tr><th>#</th><th>Type</th><th>No.</th><th>Label</th><th>Target from previous</th><th>Check penalties</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>';
    }
    function findItinerary(id) {
      var n = parseInt(id, 10);
      for (var i = 0; i < lastItinerary.length; i++) {
        if (lastItinerary[i].id === n || lastItinerary[i].id == id) return lastItinerary[i];
      }
      return null;
    }
    function showItineraryModal(existing) {
      var overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      var isFirst = !existing && lastItinerary.length === 0;
      var idx = existing ? findItineraryIndex(existing.id) : -1;
      var showTarget = existing ? (idx > 0) : !isFirst;
      var type = 'TC';
      var num = isFirst ? '0' : '';
      if (existing) {
        type = existing.controlType || (String(existing.code || '').toUpperCase().indexOf('SS') === 0 ? 'SS' : 'TC');
        num = existing.number != null && String(existing.number) !== ''
          ? String(existing.number)
          : String(existing.code || '').replace(/^TC|^SS/i, '');
      }
      var checkYes = !existing || existing.checkPenalties !== false;
      var p = existing || { name: '', targetMinutesFromPrev: isFirst ? 0 : 50 };
      overlay.innerHTML =
        '<div class="modal"><h3 style="margin:0 0 12px 0;color:#ffb74d;">' + (existing ? 'Edit control' : 'Add control') + '</h3>' +
        '<div class="row-2">' +
          '<div><label>Type</label><select id="itType"><option value="TC"' + (type === 'TC' ? ' selected' : '') + '>TC</option><option value="SS"' + (type === 'SS' ? ' selected' : '') + '>SS</option></select></div>' +
          '<div><label>Number</label><input type="text" id="itNumber" placeholder="e.g. 0, 01, 1, 6A" value="' + escapeHtml(num) + '"></div>' +
        '</div>' +
        '<label>Name (optional)</label><input type="text" id="itName" value="' + escapeHtml(p.name || '') + '">' +
        (showTarget
          ? '<label>Target minutes from previous</label><input type="number" id="itTargetMin" min="0" step="1" value="' + escapeHtml(String(p.targetMinutesFromPrev != null ? p.targetMinutesFromPrev : 50)) + '">'
          : '<p class="hint" style="margin-top:12px;">Start control — cars get their start time when they punch here.</p><input type="hidden" id="itTargetMin" value="0">') +
        (showTarget
          ? ('<label>Check penalties for this control?</label><select id="itCheckPen"><option value="yes"' + (checkYes ? ' selected' : '') + '>Yes — apply early/late penalties</option><option value="no"' + (!checkYes ? ' selected' : '') + '>No — do not create penalties</option></select>')
          : '<input type="hidden" id="itCheckPen" value="no">') +
        '<div class="modal-btns"><button type="button" class="cancel-btn">Cancel</button><button type="button" class="save-btn">Save</button></div></div>';
      document.body.appendChild(overlay);
      overlay.querySelector('.cancel-btn').onclick = function() { document.body.removeChild(overlay); };
      overlay.querySelector('.save-btn').onclick = function() {
        var controlType = overlay.querySelector('#itType').value;
        var number = overlay.querySelector('#itNumber').value.trim();
        if (!number) { alert('Number is required'); return; }
        var mins = parseInt(overlay.querySelector('#itTargetMin').value, 10);
        if (isNaN(mins) || mins < 0) mins = 0;
        var checkPenalties = overlay.querySelector('#itCheckPen').value === 'yes';
        var body = {
          controlType: controlType,
          number: number,
          name: overlay.querySelector('#itName').value.trim(),
          targetMinutesFromPrev: mins,
          checkPenalties: checkPenalties
        };
        var req = existing
          ? fetch('/itinerary/' + existing.id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
          : fetch('/itinerary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        req.then(function(r) {
          if (r.ok) { document.body.removeChild(overlay); refreshItinerary(); refreshSchedulePreview(); }
          else r.json().then(function(j) { alert((j && j.error) || 'Save failed'); }).catch(function() { alert('Save failed'); });
        });
      };
      overlay.onclick = function(ev) { if (ev.target === overlay) document.body.removeChild(overlay); };
    }
    function findItineraryIndex(id) {
      for (var i = 0; i < lastItinerary.length; i++) {
        if (lastItinerary[i].id == id) return i;
      }
      return -1;
    }
    function refreshSchedulePreview() {
      fetch('/schedule-check?t=' + Date.now())
        .then(function(r) { return r.json(); })
        .then(function(rows) {
          var el = document.getElementById('schedulePreview');
          if (!rows || !rows.length) {
            el.innerHTML = '<div class="empty">No matching car times for consecutive itinerary controls yet.</div>';
            return;
          }
          var html = rows.map(function(r) {
            var badge = r.kind === 'late' ? '<span class="badge badge-late">LATE ' + r.minutes + 'm</span>'
              : r.kind === 'early' ? '<span class="badge badge-early">EARLY ' + r.minutes + 'm</span>'
              : r.kind === 'skipped' ? '<span class="badge badge-skip">NO CHECK</span>'
              : '<span class="badge badge-ok">OK</span>';
            return '<tr>' +
              '<td>#' + escapeHtml(String(r.carNumber)) + '</td>' +
              '<td class="muted">' + escapeHtml(r.fromTc) + ' → ' + escapeHtml(r.toTc) + '</td>' +
              '<td class="muted">' + escapeHtml(String(r.targetMinutes)) + ' min</td>' +
              '<td>' + escapeHtml(r.prevTime) + '</td>' +
              '<td>' + escapeHtml(r.targetTime) + '</td>' +
              '<td>' + escapeHtml(r.actualTime) + '</td>' +
              '<td>' + badge + '</td>' +
              '<td>' + (r.kind === 'ok' || r.kind === 'skipped' ? '—' : escapeHtml(r.penalty)) + '</td>' +
              '</tr>';
          }).join('');
          el.innerHTML = '<table class="data"><thead><tr><th>Car</th><th>Leg</th><th>Target</th><th>Prev punch</th><th>Due</th><th>Actual</th><th>Status</th><th>Penalty</th></tr></thead><tbody>' + html + '</tbody></table>';
        })
        .catch(function() {
          document.getElementById('schedulePreview').innerHTML = '<div class="empty">Could not load schedule check.</div>';
        });
    }
    document.getElementById('addItineraryBtn').onclick = function() { showItineraryModal(null); };
    document.getElementById('recalcFromItineraryBtn').onclick = function() {
      runRecalculate().then(function() { showTab('penalties'); });
    };
    document.getElementById('resetItineraryBtn').onclick = function() {
      if (!confirm('Clear the whole itinerary?')) return;
      fetch('/reset-itinerary', { method: 'POST' }).then(function(r) { if (r.ok) { refreshItinerary(); refreshSchedulePreview(); } });
    };
    document.getElementById('itineraryList').addEventListener('click', function(ev) {
      var edit = ev.target.closest('.it-edit');
      if (edit) { var item = findItinerary(edit.getAttribute('data-id')); if (item) showItineraryModal(item); return; }
      var del = ev.target.closest('.it-del');
      if (del) {
        if (!confirm('Delete this time control?')) return;
        fetch('/itinerary/' + del.getAttribute('data-id'), { method: 'DELETE' })
          .then(function(r) { if (r.ok) { refreshItinerary(); refreshSchedulePreview(); } });
        return;
      }
      var up = ev.target.closest('.it-up');
      if (up) {
        fetch('/itinerary/' + up.getAttribute('data-id') + '/move', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ direction: 'up' }) })
          .then(function(r) { if (r.ok) { refreshItinerary(); refreshSchedulePreview(); } });
        return;
      }
      var down = ev.target.closest('.it-down');
      if (down) {
        fetch('/itinerary/' + down.getAttribute('data-id') + '/move', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ direction: 'down' }) })
          .then(function(r) { if (r.ok) { refreshItinerary(); refreshSchedulePreview(); } });
      }
    });

    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


@app.route("/entries")
def get_entries():
    for i, e in enumerate(entries):
        if "id" not in e:
            e["id"] = i
    r = jsonify(entries)
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return r


@app.route("/entry", methods=["POST"])
def add_entry():
    global _next_entry_id
    data = request.get_json(force=True, silent=True) or {}
    time = str(data.get("time", ""))
    try:
        car_number = int(data.get("carNumber", 0))
    except (TypeError, ValueError):
        car_number = 0
    tc = str(data.get("tc") or "")
    entry = {"id": _next_entry_id, "time": time, "carNumber": car_number, "tc": tc}
    _next_entry_id += 1
    entries.insert(0, entry)
    # Keep penalties fresh when new punches arrive
    recalculate_auto_penalties()
    return jsonify({"ok": True, "id": entry["id"]}), 201


@app.route("/entry/<int:entry_id>", methods=["PUT"])
def update_entry(entry_id):
    entry = next((e for e in entries if e.get("id") == entry_id), None)
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    if "time" in data:
        entry["time"] = str(data["time"])
    if "carNumber" in data:
        try:
            entry["carNumber"] = int(data["carNumber"])
        except (TypeError, ValueError):
            pass
    if "tc" in data:
        entry["tc"] = str(data["tc"])
    recalculate_auto_penalties()
    return jsonify({"ok": True}), 200


@app.route("/entry/<int:entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    global entries
    for i, e in enumerate(entries):
        if e.get("id") == entry_id:
            entries.pop(i)
            recalculate_auto_penalties()
            return jsonify({"ok": True}), 200
    return jsonify({"error": "Not found"}), 404


@app.route("/reset-entries", methods=["POST"])
def reset_entries():
    global entries
    entries.clear()
    recalculate_auto_penalties()
    return jsonify({"ok": True}), 200


# ---------- Penalties ----------
@app.route("/penalties")
def get_penalties():
    r = jsonify(penalties)
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return r


@app.route("/penalties", methods=["POST"])
def add_penalty():
    global _next_penalty_id
    data = request.get_json(force=True, silent=True) or {}
    try:
        car_number = int(data.get("carNumber", 0))
    except (TypeError, ValueError):
        car_number = 0
    item = {
        "id": _next_penalty_id,
        "carNumber": car_number,
        "penalty": str(data.get("penalty") or ""),
        "tc": str(data.get("tc") or ""),
        "reason": str(data.get("reason") or ""),
        "kind": str(data.get("kind") or "manual"),
        "source": str(data.get("source") or "manual"),
    }
    _next_penalty_id += 1
    penalties.append(item)
    return jsonify({"ok": True, "id": item["id"]}), 201


@app.route("/penalties/<int:penalty_id>", methods=["PUT"])
def update_penalty(penalty_id):
    item = next((p for p in penalties if p.get("id") == penalty_id), None)
    if item is None:
        return jsonify({"error": "Not found"}), 404
    if item.get("source") == "auto":
        return jsonify({"error": "Auto penalties are managed by recalculate"}), 400
    data = request.get_json(force=True, silent=True) or {}
    if "carNumber" in data:
        try:
            item["carNumber"] = int(data["carNumber"])
        except (TypeError, ValueError):
            pass
    if "penalty" in data:
        item["penalty"] = str(data["penalty"])
    if "tc" in data:
        item["tc"] = str(data["tc"])
    if "reason" in data:
        item["reason"] = str(data["reason"])
    item["source"] = "manual"
    return jsonify({"ok": True}), 200


@app.route("/penalties/<int:penalty_id>", methods=["DELETE"])
def delete_penalty(penalty_id):
    for i, p in enumerate(penalties):
        if p.get("id") == penalty_id:
            penalties.pop(i)
            return jsonify({"ok": True}), 200
    return jsonify({"error": "Not found"}), 404


@app.route("/reset-penalties", methods=["POST"])
def reset_penalties():
    global penalties
    data = request.get_json(force=True, silent=True) or {}
    if data.get("autoOnly"):
        penalties[:] = [p for p in penalties if p.get("source") != "auto"]
    else:
        penalties.clear()
    return jsonify({"ok": True}), 200


@app.route("/recalculate-penalties", methods=["POST"])
def recalculate_penalties_route():
    result = recalculate_auto_penalties()
    return jsonify(result), 200


# ---------- Itinerary ----------
@app.route("/itinerary")
def get_itinerary():
    r = jsonify(itinerary)
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return r


@app.route("/itinerary", methods=["POST"])
def add_itinerary():
    global _next_itinerary_id
    data = request.get_json(force=True, silent=True) or {}
    is_first = not itinerary
    item = itinerary_item_from_payload(data, is_first=is_first)
    if not item["code"]:
        return jsonify({"error": "Control type and number are required"}), 400
    item["id"] = _next_itinerary_id
    _next_itinerary_id += 1
    itinerary.append(item)
    recalculate_auto_penalties()
    return jsonify({"ok": True, "id": item["id"]}), 201


@app.route("/itinerary/<int:item_id>", methods=["PUT"])
def update_itinerary(item_id):
    item = next((x for x in itinerary if x.get("id") == item_id), None)
    if item is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    idx = next(i for i, x in enumerate(itinerary) if x.get("id") == item_id)
    merged = {
        "controlType": data.get("controlType", item.get("controlType", "TC")),
        "number": data.get("number", item.get("number", "")),
        "code": data.get("code", item.get("code", "")),
        "name": data.get("name", item.get("name", "")),
        "targetMinutesFromPrev": data.get(
            "targetMinutesFromPrev", item.get("targetMinutesFromPrev", 0)
        ),
        "checkPenalties": data.get(
            "checkPenalties", item.get("checkPenalties", True)
        ),
    }
    updated = itinerary_item_from_payload(merged, is_first=(idx == 0))
    if not updated["code"]:
        return jsonify({"error": "Control type and number are required"}), 400
    item.update(updated)
    recalculate_auto_penalties()
    return jsonify({"ok": True}), 200


@app.route("/itinerary/<int:item_id>", methods=["DELETE"])
def delete_itinerary(item_id):
    for i, item in enumerate(itinerary):
        if item.get("id") == item_id:
            itinerary.pop(i)
            if itinerary:
                itinerary[0]["targetMinutesFromPrev"] = 0
            recalculate_auto_penalties()
            return jsonify({"ok": True}), 200
    return jsonify({"error": "Not found"}), 404


@app.route("/itinerary/<int:item_id>/move", methods=["POST"])
def move_itinerary(item_id):
    data = request.get_json(force=True, silent=True) or {}
    direction = str(data.get("direction") or "")
    idx = next((i for i, x in enumerate(itinerary) if x.get("id") == item_id), None)
    if idx is None:
        return jsonify({"error": "Not found"}), 404
    if direction == "up" and idx > 0:
        itinerary[idx - 1], itinerary[idx] = itinerary[idx], itinerary[idx - 1]
    elif direction == "down" and idx < len(itinerary) - 1:
        itinerary[idx + 1], itinerary[idx] = itinerary[idx], itinerary[idx + 1]
    else:
        return jsonify({"ok": True}), 200
    if itinerary:
        itinerary[0]["targetMinutesFromPrev"] = 0
    recalculate_auto_penalties()
    return jsonify({"ok": True}), 200


@app.route("/reset-itinerary", methods=["POST"])
def reset_itinerary():
    itinerary.clear()
    recalculate_auto_penalties()
    return jsonify({"ok": True}), 200


@app.route("/schedule-check")
def schedule_check():
    """Preview target vs actual for every car on every itinerary leg."""
    rows = []
    if len(itinerary) < 2:
        return jsonify(rows)
    cars = sorted({int(e.get("carNumber", 0)) for e in entries})
    for i in range(1, len(itinerary)):
        prev = itinerary[i - 1]
        curr = itinerary[i]
        prev_code = normalize_tc(prev.get("code"))
        curr_code = normalize_tc(curr.get("code"))
        try:
            target_minutes = int(curr.get("targetMinutesFromPrev") or 0)
        except (TypeError, ValueError):
            target_minutes = 0
        check = parse_bool(curr.get("checkPenalties"), default=True)
        for car in cars:
            prev_t = official_time_for_car_tc(car, prev_code)
            curr_t = official_time_for_car_tc(car, curr_code)
            if prev_t is None or curr_t is None:
                continue
            if not check:
                target_arrival = prev_t + timedelta(minutes=int(target_minutes))
                rows.append({
                    "carNumber": car,
                    "fromTc": prev_code,
                    "toTc": curr_code,
                    "targetMinutes": target_minutes,
                    "prevTime": format_clock(prev_t),
                    "targetTime": format_clock(target_arrival),
                    "actualTime": format_clock(curr_t),
                    "kind": "skipped",
                    "minutes": 0,
                    "penalty": "—",
                    "reason": "Penalty check disabled for this control",
                    "checkPenalties": False,
                })
                continue
            result = compute_leg_penalty(prev_t, curr_t, target_minutes)
            rows.append({
                "carNumber": car,
                "fromTc": prev_code,
                "toTc": curr_code,
                "targetMinutes": target_minutes,
                "prevTime": format_clock(prev_t),
                "targetTime": result["targetTime"],
                "actualTime": result["actualTime"],
                "kind": result["kind"],
                "minutes": result["minutes"],
                "penalty": result["penalty"],
                "reason": result["reason"],
                "checkPenalties": True,
            })
    r = jsonify(rows)
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return r


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port, debug=False)

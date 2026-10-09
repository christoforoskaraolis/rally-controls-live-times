"""
Rally Controls Live Times – web server for the Rally Control Timer app.
"""
from flask import Flask, request, jsonify
import os

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

itinerary = []
_next_itinerary_id = 0


@app.route("/")
def index():
    return """
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
    .entry-actions button { padding: 4px 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }
    .entry-actions .edit-btn { background: #555; color: #ffb74d; }
    .entry-actions .delete-btn { background: #c62828; color: #fff; }
    .entry-actions .move-tc-select { padding: 4px 6px; background: #2a2a2a; color: #ffb74d; border: 1px solid #444; border-radius: 4px; font-size: 12px; cursor: pointer; min-width: 72px; }
    .empty { color: #666; padding: 24px 0; }
    .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; }
    .modal { background: #2a2a2a; padding: 20px; border-radius: 8px; min-width: 280px; max-width: 92vw; }
    .modal label { display: block; color: #aaa; font-size: 12px; margin-top: 10px; margin-bottom: 4px; }
    .modal input, .modal select, .modal textarea {
      width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px;
      color: #fff; font-size: 14px; box-sizing: border-box; font-family: inherit;
    }
    .modal textarea { min-height: 72px; resize: vertical; }
    .modal-btns { margin-top: 16px; display: flex; gap: 8px; justify-content: flex-end; }
    .modal-btns button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
    .modal-btns .save-btn { background: #ffb74d; color: #1a1a1a; }
    .modal-btns .cancel-btn { background: #555; color: #fff; }
    #list, #penaltyList, #itineraryList { max-width: 720px; }
    .tc-block { margin-bottom: 24px; }
    .tc-title { font-size: 1.1rem; color: #ffb74d; margin: 0 0 8px 0; padding-bottom: 4px; border-bottom: 1px solid #444; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
    .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
    .btn-danger { background: #c62828; color: #fff; }
    .btn-primary { background: #ffb74d; color: #1a1a1a; font-weight: 700; }
    .hint { color: #888; font-size: 14px; margin: 0 0 12px 0; }
    .meta { color: #666; font-size: 12px; margin: 0 0 12px 0; }
    table.data { width: 100%; border-collapse: collapse; max-width: 720px; }
    table.data th, table.data td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #333; vertical-align: top; }
    table.data th { color: #aaa; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
    table.data td { color: #ffb74d; font-size: 15px; }
    table.data td.muted { color: #ccc; }
    table.data td.actions { white-space: nowrap; }
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
      <button type="button" class="btn btn-danger" id="resetPenaltiesBtn">Clear penalties</button>
    </div>
    <p class="hint">Track time penalties by car. Saved on this server (in memory until restart).</p>
    <div id="penaltyList">
      <div class="empty">No penalties yet.</div>
    </div>
  </section>

  <!-- ITINERARY -->
  <section id="panel-itinerary" class="tab-panel" role="tabpanel" hidden>
    <div class="toolbar">
      <button type="button" class="btn btn-primary" id="addItineraryBtn">Add item</button>
      <button type="button" class="btn btn-danger" id="resetItineraryBtn">Clear itinerary</button>
    </div>
    <p class="hint">Event itinerary: controls, stages, distances and notes.</p>
    <div id="itineraryList">
      <div class="empty">No itinerary items yet.</div>
    </div>
  </section>

  <script>
    function escapeHtml(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }

    /* ---------- Tabs ---------- */
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
      if (name === 'itinerary') refreshItinerary();
    }
    document.querySelectorAll('.tab').forEach(function(btn) {
      btn.addEventListener('click', function() { showTab(btn.getAttribute('data-tab')); });
    });

    /* ---------- Live times (existing behaviour) ---------- */
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
      var editCar = overlay.querySelector('#editCar');
      var editTime = overlay.querySelector('#editTime');
      overlay.querySelector('.cancel-btn').onclick = function() { document.body.removeChild(overlay); };
      overlay.querySelector('.save-btn').onclick = function() {
        var car = parseInt(editCar.value, 10);
        if (isNaN(car) || car < 0 || car > 99) { alert('Car number must be 0–99'); return; }
        var time = editTime.value.trim();
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
        var id = btn.getAttribute('data-id');
        fetch('/entry/' + id, { method: 'DELETE' }).then(function(r) { if (r.ok) refresh(); }).catch(function() { alert('Delete failed'); });
      }
    });
    document.getElementById('list').addEventListener('change', function(ev) {
      var sel = ev.target.closest('.move-tc-select');
      if (!sel) return;
      var id = sel.getAttribute('data-id');
      var entry = findEntryById(id);
      if (!entry) return;
      var newTc = sel.value;
      var currentTc = (entry.tc != null && entry.tc !== '') ? String(entry.tc).trim() : '';
      if (newTc === currentTc) return;
      fetch('/entry/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tc: newTc }) })
        .then(function(r) { if (r.ok) refresh(); else alert('Move failed'); })
        .catch(function() { alert('Move failed'); });
    });
    document.getElementById('tcFilter').onchange = function() { renderList(lastData, this.value); };
    document.getElementById('resetBtn').onclick = function() {
      if (!confirm('Are you sure you want to delete all times?')) return;
      fetch('/reset-entries', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
        .then(function(r) { if (r.ok) refresh(); }).catch(function() { alert('Reset failed'); });
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
        el.innerHTML = '<div class="empty">No penalties yet.</div>';
        return;
      }
      var rows = lastPenalties.map(function(p, i) {
        return '<tr data-id="' + p.id + '">' +
          '<td class="muted">' + (i + 1) + '</td>' +
          '<td>#' + escapeHtml(String(p.carNumber)) + '</td>' +
          '<td>' + escapeHtml(p.penalty || '') + '</td>' +
          '<td class="muted">' + escapeHtml(p.tc || '') + '</td>' +
          '<td class="muted">' + escapeHtml(p.reason || '') + '</td>' +
          '<td class="actions"><button type="button" class="edit-btn pen-edit" data-id="' + p.id + '">Edit</button> ' +
          '<button type="button" class="delete-btn pen-del" data-id="' + p.id + '">Delete</button></td>' +
          '</tr>';
      }).join('');
      el.innerHTML = '<table class="data"><thead><tr><th>#</th><th>Car</th><th>Penalty</th><th>TC / Stage</th><th>Reason</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>';
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
        '<label>Penalty (e.g. +0:10 or 10s)</label><input type="text" id="penVal" value="' + escapeHtml(p.penalty || '') + '">' +
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
          reason: overlay.querySelector('#penReason').value.trim()
        };
        var req = existing
          ? fetch('/penalties/' + existing.id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
          : fetch('/penalties', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        req.then(function(r) { if (r.ok) { document.body.removeChild(overlay); refreshPenalties(); } else alert('Save failed'); })
          .catch(function() { alert('Save failed'); });
      };
      overlay.onclick = function(ev) { if (ev.target === overlay) document.body.removeChild(overlay); };
    }
    document.getElementById('addPenaltyBtn').onclick = function() { showPenaltyModal(null); };
    document.getElementById('resetPenaltiesBtn').onclick = function() {
      if (!confirm('Clear all penalties?')) return;
      fetch('/reset-penalties', { method: 'POST' }).then(function(r) { if (r.ok) refreshPenalties(); });
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
        el.innerHTML = '<div class="empty">No itinerary items yet.</div>';
        return;
      }
      var rows = lastItinerary.map(function(item, i) {
        return '<tr data-id="' + item.id + '">' +
          '<td class="muted">' + (i + 1) + '</td>' +
          '<td>' + escapeHtml(item.code || '') + '</td>' +
          '<td class="muted">' + escapeHtml(item.name || '') + '</td>' +
          '<td>' + escapeHtml(item.distance || '') + '</td>' +
          '<td>' + escapeHtml(item.targetTime || '') + '</td>' +
          '<td class="muted">' + escapeHtml(item.notes || '') + '</td>' +
          '<td class="actions"><button type="button" class="edit-btn it-edit" data-id="' + item.id + '">Edit</button> ' +
          '<button type="button" class="delete-btn it-del" data-id="' + item.id + '">Delete</button></td>' +
          '</tr>';
      }).join('');
      el.innerHTML = '<table class="data"><thead><tr><th>#</th><th>Code</th><th>Name</th><th>Distance</th><th>Target</th><th>Notes</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>';
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
      var p = existing || { code: '', name: '', distance: '', targetTime: '', notes: '' };
      overlay.innerHTML =
        '<div class="modal"><h3 style="margin:0 0 12px 0;color:#ffb74d;">' + (existing ? 'Edit itinerary item' : 'Add itinerary item') + '</h3>' +
        '<label>Code (e.g. TC1, SS2)</label><input type="text" id="itCode" value="' + escapeHtml(p.code || '') + '">' +
        '<label>Name</label><input type="text" id="itName" value="' + escapeHtml(p.name || '') + '">' +
        '<label>Distance (e.g. 12.4 km)</label><input type="text" id="itDist" value="' + escapeHtml(p.distance || '') + '">' +
        '<label>Target time</label><input type="text" id="itTarget" value="' + escapeHtml(p.targetTime || '') + '">' +
        '<label>Notes</label><textarea id="itNotes">' + escapeHtml(p.notes || '') + '</textarea>' +
        '<div class="modal-btns"><button type="button" class="cancel-btn">Cancel</button><button type="button" class="save-btn">Save</button></div></div>';
      document.body.appendChild(overlay);
      overlay.querySelector('.cancel-btn').onclick = function() { document.body.removeChild(overlay); };
      overlay.querySelector('.save-btn').onclick = function() {
        var body = {
          code: overlay.querySelector('#itCode').value.trim(),
          name: overlay.querySelector('#itName').value.trim(),
          distance: overlay.querySelector('#itDist').value.trim(),
          targetTime: overlay.querySelector('#itTarget').value.trim(),
          notes: overlay.querySelector('#itNotes').value.trim()
        };
        if (!body.code && !body.name) { alert('Enter at least a code or name'); return; }
        var req = existing
          ? fetch('/itinerary/' + existing.id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
          : fetch('/itinerary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        req.then(function(r) { if (r.ok) { document.body.removeChild(overlay); refreshItinerary(); } else alert('Save failed'); })
          .catch(function() { alert('Save failed'); });
      };
      overlay.onclick = function(ev) { if (ev.target === overlay) document.body.removeChild(overlay); };
    }
    document.getElementById('addItineraryBtn').onclick = function() { showItineraryModal(null); };
    document.getElementById('resetItineraryBtn').onclick = function() {
      if (!confirm('Clear the whole itinerary?')) return;
      fetch('/reset-itinerary', { method: 'POST' }).then(function(r) { if (r.ok) refreshItinerary(); });
    };
    document.getElementById('itineraryList').addEventListener('click', function(ev) {
      var edit = ev.target.closest('.it-edit');
      if (edit) { var item = findItinerary(edit.getAttribute('data-id')); if (item) showItineraryModal(item); return; }
      var del = ev.target.closest('.it-del');
      if (del) {
        if (!confirm('Delete this itinerary item?')) return;
        fetch('/itinerary/' + del.getAttribute('data-id'), { method: 'DELETE' })
          .then(function(r) { if (r.ok) refreshItinerary(); });
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
    return jsonify({"ok": True}), 200


@app.route("/entry/<int:entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    global entries
    for i, e in enumerate(entries):
        if e.get("id") == entry_id:
            entries.pop(i)
            return jsonify({"ok": True}), 200
    return jsonify({"error": "Not found"}), 404


@app.route("/reset-entries", methods=["POST"])
def reset_entries():
    global entries
    entries.clear()
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
    }
    _next_penalty_id += 1
    penalties.append(item)
    return jsonify({"ok": True, "id": item["id"]}), 201


@app.route("/penalties/<int:penalty_id>", methods=["PUT"])
def update_penalty(penalty_id):
    item = next((p for p in penalties if p.get("id") == penalty_id), None)
    if item is None:
        return jsonify({"error": "Not found"}), 404
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
    penalties.clear()
    return jsonify({"ok": True}), 200


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
    item = {
        "id": _next_itinerary_id,
        "code": str(data.get("code") or ""),
        "name": str(data.get("name") or ""),
        "distance": str(data.get("distance") or ""),
        "targetTime": str(data.get("targetTime") or ""),
        "notes": str(data.get("notes") or ""),
    }
    _next_itinerary_id += 1
    itinerary.append(item)
    return jsonify({"ok": True, "id": item["id"]}), 201


@app.route("/itinerary/<int:item_id>", methods=["PUT"])
def update_itinerary(item_id):
    item = next((x for x in itinerary if x.get("id") == item_id), None)
    if item is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    for key in ("code", "name", "distance", "targetTime", "notes"):
        if key in data:
            item[key] = str(data[key])
    return jsonify({"ok": True}), 200


@app.route("/itinerary/<int:item_id>", methods=["DELETE"])
def delete_itinerary(item_id):
    for i, item in enumerate(itinerary):
        if item.get("id") == item_id:
            itinerary.pop(i)
            return jsonify({"ok": True}), 200
    return jsonify({"error": "Not found"}), 404


@app.route("/reset-itinerary", methods=["POST"])
def reset_itinerary():
    itinerary.clear()
    return jsonify({"ok": True}), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port, debug=False)

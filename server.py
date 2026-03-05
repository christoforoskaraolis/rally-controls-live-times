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
    .entry { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #333; font-size: 1.25rem; gap: 8px; }
    .entry .num-car { color: #ccc; }
    .entry .time { font-variant-numeric: tabular-nums; color: #ffb74d; }
    .entry-actions { display: flex; gap: 6px; flex-shrink: 0; }
    .entry-actions button { padding: 4px 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }
    .entry-actions .edit-btn { background: #555; color: #ffb74d; }
    .entry-actions .delete-btn { background: #c62828; color: #fff; }
    .empty { color: #666; padding: 24px 0; }
    .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; }
    .modal { background: #2a2a2a; padding: 20px; border-radius: 8px; min-width: 280px; }
    .modal label { display: block; color: #aaa; font-size: 12px; margin-top: 10px; margin-bottom: 4px; }
    .modal input { width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px; color: #fff; font-size: 14px; box-sizing: border-box; }
    .modal-btns { margin-top: 16px; display: flex; gap: 8px; justify-content: flex-end; }
    .modal-btns button { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
    .modal-btns .save-btn { background: #ffb74d; color: #1a1a1a; }
    .modal-btns .cancel-btn { background: #555; color: #fff; }
    #list { max-width: 560px; }
    .tc-block { margin-bottom: 24px; }
    .tc-title { font-size: 1.1rem; color: #ffb74d; margin: 0 0 8px 0; padding-bottom: 4px; border-bottom: 1px solid #444; }
  </style>
</head>
<body>
  <h1>Rally Controls Live Times</h1>
  <p>
    <button type="button" id="resetBtn" style="padding:8px 16px;background:#c62828;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px;">Reset all times</button>
  </p>
  <p style="color:#888;font-size:14px;">Auto-refreshing every 3 seconds. Split by TC. Oldest first.</p>
  <p style="margin:12px 0 4px 0;">
    <label for="tcFilter" style="color:#aaa;font-size:14px;">Show entries: </label>
    <select id="tcFilter" style="padding:6px 10px;background:#2a2a2a;color:#ffb74d;border:1px solid #444;border-radius:6px;font-size:14px;min-width:140px;">
      <option value="__all__">All TCs</option>
    </select>
  </p>
  <p id="lastUpdate" style="color:#666;font-size:12px;margin-top:-8px;">Last updated: --</p>
  <div id="list">
    <div class="empty">No entries yet. Record a time on the app to see it here.</div>
  </div>
  <script>
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
    function escapeHtml(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
    var lastData = [];
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
          return '<div class="entry" data-id="' + id + '"><span class="num-car">' + (i+1) + '. #' + escapeHtml(String(e.carNumber)) + '</span><span class="time">' + escapeHtml(e.time) + '</span><div class="entry-actions"><button type="button" class="edit-btn" data-id="' + id + '">Edit</button><button type="button" class="delete-btn" data-id="' + id + '">Delete</button></div></div>';
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
    document.getElementById('tcFilter').onchange = function() { renderList(lastData, this.value); };
    document.getElementById('resetBtn').onclick = function() {
      if (!confirm('Are you sure you want to delete all times?')) return;
      fetch('/reset-entries', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
        .then(function(r) { if (r.ok) refresh(); }).catch(function() { alert('Reset failed'); });
    };
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


@app.route("/entries")
def get_entries():
    # Ensure every entry has an id for edit/delete
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


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port, debug=False)

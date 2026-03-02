"""
Rally Controls Live Times – web server for the Rally Control Timer app.
"""
from flask import Flask, request, jsonify
import os

app = Flask(__name__, static_folder=None)


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


entries = []


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
    .entry { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #333; font-size: 1.25rem; }
    .entry .num-car { color: #ccc; }
    .entry .time { font-variant-numeric: tabular-nums; color: #ffb74d; }
    .empty { color: #666; padding: 24px 0; }
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
          return '<div class="entry"><span class="num-car">' + (i+1) + '. #' + escapeHtml(String(e.carNumber)) + '</span><span class="time">' + escapeHtml(e.time) + '</span></div>';
        }).join('');
        return '<div class="tc-block"><h2 class="tc-title">' + escapeHtml(displayTc(tcKey)) + '</h2>' + rows + '</div>';
      }).join('');
    }
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
    r = jsonify(entries)
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return r


@app.route("/entry", methods=["POST"])
def add_entry():
    data = request.get_json(force=True, silent=True) or {}
    time = str(data.get("time", ""))
    try:
        car_number = int(data.get("carNumber", 0))
    except (TypeError, ValueError):
        car_number = 0
    tc = str(data.get("tc") or "")
    entries.insert(0, {"time": time, "carNumber": car_number, "tc": tc})
    return jsonify({"ok": True}), 201


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

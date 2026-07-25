/* Apollo Streaming Lab - front-end glue. Vanilla JS, no build step. */
const ASL = (() => {
  const sid = () => document.getElementById("session")?.dataset.id;

  async function api(method, path, body, isForm) {
    const opts = { method, headers: {} };
    if (body && !isForm) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    if (body && isForm) { opts.body = body; }
    const r = await fetch(path, opts);
    if (!r.ok) { throw new Error(`${r.status} ${await r.text()}`); }
    return r.status === 204 ? null : r.json();
  }

  function wireNewSessionForm() {
    const form = document.getElementById("new-session");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = new FormData(form);
      const payload = {
        name: f.get("name") || null,
        host: f.get("host") || null,
        client: f.get("client") || null,
        network_path: f.get("network_path") || null,
        codec: f.get("codec") || null,
        resolution: f.get("resolution") || null,
        fps: f.get("fps") ? Number(f.get("fps")) : null,
        bitrate_mbps: f.get("bitrate_mbps") ? Number(f.get("bitrate_mbps")) : null,
        hdr: f.get("hdr") === "on",
        notes: f.get("notes") || "",
      };
      const s = await api("POST", "/api/sessions", payload);
      location = `/sessions/${s.id}`;
    });
  }

  async function saveOutcome() {
    await api("PATCH", `/api/sessions/${sid()}`, { outcome: document.getElementById("outcome").value });
    flash("Outcome saved");
  }
  async function saveNotes() {
    await api("PATCH", `/api/sessions/${sid()}`, { notes: document.getElementById("notes").value });
    flash("Notes saved");
  }
  async function stopSession() { await api("POST", `/api/sessions/${sid()}/stop`); location.reload(); }
  async function deleteSession() {
    if (!confirm("Delete this session and all its data?")) return;
    await api("DELETE", `/api/sessions/${sid()}`); location = "/";
  }

  async function analyze() {
    const el = document.getElementById("diagnosis");
    el.innerHTML = "<p class='muted'>Analyzing…</p>";
    try {
      const r = await api("POST", `/api/sessions/${sid()}/analyze`);
      el.innerHTML = "<pre></pre>"; el.querySelector("pre").textContent = r.diagnosis;
    } catch (e) { el.innerHTML = `<p class='warn'>${e.message}</p>`; }
  }

  function wireChat() {
    const form = document.getElementById("chat-form");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = document.getElementById("chat-input");
      const msg = input.value.trim(); if (!msg) return;
      addMsg("user", msg); input.value = "";
      try { const r = await api("POST", `/api/sessions/${sid()}/chat`, { message: msg }); addMsg("assistant", r.reply); }
      catch (e2) { addMsg("assistant", "error: " + e2.message); }
    });
  }
  function addMsg(role, content) {
    const box = document.getElementById("chat");
    const d = document.createElement("div"); d.className = "msg " + role;
    d.innerHTML = `<b>${role}:</b> <span></span>`; d.querySelector("span").textContent = content;
    box.appendChild(d); box.scrollTop = box.scrollHeight;
  }

  function wireArtifactUpload() {
    const form = document.getElementById("artifact-form");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      await api("POST", `/api/sessions/${sid()}/artifacts`, new FormData(form), true);
      location.reload();
    });
  }

  function applyLogFilter() {
    const q = document.getElementById("log-filter").value.toLowerCase();
    const hl = document.getElementById("hl").checked;
    for (const id of ["host-log", "client-log"]) {
      const pre = document.getElementById(id);
      if (!pre.dataset.raw) pre.dataset.raw = pre.textContent;
      const lines = pre.dataset.raw.split("\n").filter(l => !q || l.toLowerCase().includes(q));
      pre.innerHTML = "";
      for (const line of lines) {
        const span = document.createElement("span"); span.textContent = line + "\n";
        if (hl && /error|fail|disconnect|timeout|packet loss|unable|refused|fatal|crash/i.test(line)) span.className = "err";
        pre.appendChild(span);
      }
    }
  }

  function wireSyncScroll() {
    const h = document.getElementById("host-log"), c = document.getElementById("client-log");
    if (!h || !c) return;
    let lock = false;
    const mk = (a, b) => () => {
      if (!document.getElementById("sync").checked || lock) return;
      lock = true; b.scrollTop = a.scrollTop; lock = false;
    };
    h.addEventListener("scroll", mk(h, c)); c.addEventListener("scroll", mk(c, h));
  }

  function drawRssiChart() {
    const holder = document.getElementById("rssi-chart");
    const raw = document.getElementById("bundle-data");
    if (!holder || !raw) return;
    const samples = JSON.parse(raw.textContent).filter(s => s.source === "client" && s.rssi != null);
    if (samples.length < 2) return;
    const W = 460, H = 90, pad = 24;
    const xs = samples.map((_, i) => i);
    const ys = samples.map(s => s.rssi);
    const minY = Math.min(-90, ...ys), maxY = Math.max(-30, ...ys);
    const x = i => pad + (i / (samples.length - 1)) * (W - pad * 2);
    const y = v => H - pad - ((v - minY) / (maxY - minY)) * (H - pad * 2);
    let path = samples.map((s, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(s.rssi).toFixed(1)}`).join(" ");
    let roams = "";
    for (let i = 1; i < samples.length; i++) {
      if (samples[i].bssid && samples[i - 1].bssid && samples[i].bssid !== samples[i - 1].bssid) {
        roams += `<line x1="${x(i)}" y1="4" x2="${x(i)}" y2="${H - 4}" class="roam"/>`;
      }
    }
    holder.innerHTML =
      `<svg viewBox="0 0 ${W} ${H}" class="spark"><path d="${path}" class="rssiline"/>${roams}
       <text x="2" y="12" class="axis">${maxY} dBm</text><text x="2" y="${H - 2}" class="axis">${minY} dBm</text></svg>
       <div class="muted small">RSSI over the session; red lines = access-point roam (BSSID change).</div>`;
  }

  function flash(msg) {
    const d = document.createElement("div"); d.className = "flash"; d.textContent = msg;
    document.body.appendChild(d); setTimeout(() => d.remove(), 1800);
  }

  // --- sessions index refresh while any capture is still running ---------------
  function appendTextCell(tr, text, cls) {
    const td = document.createElement("td");
    if (cls) td.className = cls;
    td.textContent = text;
    tr.appendChild(td);
  }

  function appendPillCell(tr, type, value) {
    const td = document.createElement("td");
    const span = document.createElement("span");
    span.className = `pill ${type}-${value}`;
    span.textContent = value;
    td.appendChild(span);
    tr.appendChild(td);
  }

  function renderSessionRows(sessions) {
    const tb = document.getElementById("sessions-tbody"); if (!tb) return false;
    const rows = [];
    for (const s of sessions) {
      const id = String(s.id || "");
      const href = `/sessions/${id}`;
      const tr = document.createElement("tr");
      tr.onclick = () => { location = href; };

      const nameTd = document.createElement("td");
      const link = document.createElement("a");
      link.href = href;
      link.textContent = s.name || id;
      const br = document.createElement("br");
      const idSpan = document.createElement("span");
      idSpan.className = "muted mono";
      idSpan.textContent = id;
      nameTd.appendChild(link);
      nameTd.appendChild(br);
      nameTd.appendChild(idSpan);
      tr.appendChild(nameTd);

      appendPillCell(tr, "status", s.status);
      appendPillCell(tr, "outcome", s.outcome);
      appendTextCell(tr, s.network_path || "—");
      appendTextCell(tr, `${s.host || "?"} → ${s.client || "?"}`);
      appendTextCell(tr, `${s.codec || "—"}${s.hdr ? " · HDR" : ""}`);
      appendTextCell(tr, (s.created_at || "").substring(0, 19), "mono");
      rows.push(tr);
    }
    tb.replaceChildren(...rows);
    return sessions.some(s => s.status === "active");
  }

  async function refreshSessionsList() {
    let sessions;
    try { sessions = await api("GET", "/api/sessions"); } catch (e) { return true; }
    return renderSessionRows(sessions || []);
  }

  function initIndexPage() {
    const table = document.getElementById("sessions-table");
    const tb = document.getElementById("sessions-tbody");
    if (!table || !tb || !tb.querySelector(".status-active")) return;
    const timer = setInterval(async () => {
      if (!(await refreshSessionsList())) clearInterval(timer);
    }, 8000);
  }

  // --- live refresh while a capture is still running ---------------------------
  function renderLinkRows(samples) {
    const tb = document.getElementById("link-tbody"); if (!tb) return;
    tb.innerHTML = "";
    if (!samples.length) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 8; td.className = "muted"; td.textContent = "No link samples.";
      tr.appendChild(td); tb.appendChild(tr); return;
    }
    for (const l of samples) {
      const tr = document.createElement("tr");
      const band = (l.band || "") + (l.channel ? "/" + l.channel : "");
      const rssi = l.rssi != null ? l.rssi : (l.signal_pct != null ? l.signal_pct + "%" : "—");
      const cells = [
        [(l.sampled_at || "").substring(11, 19), "mono"], [l.source || "—", ""],
        [l.link_type || "—", ""], [l.ssid || "—", ""], [l.bssid || "—", "mono bssid"],
        [band || "—", ""], [rssi, ""], [l.link_speed || "—", ""],
      ];
      for (const [txt, cls] of cells) {
        const td = document.createElement("td"); if (cls) td.className = cls;
        td.textContent = txt; tr.appendChild(td);
      }
      tb.appendChild(tr);
    }
  }

  function updateLogPane(id, chunks) {
    const pre = document.getElementById(id); if (!pre) return;
    const content = chunks.map(c => c.content).join("\n");
    if (pre.dataset.raw === content) return;
    const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
    pre.dataset.raw = content;
    applyLogFilter();
    if (atBottom) pre.scrollTop = pre.scrollHeight;
  }

  async function refreshOnce() {
    let b;
    try { b = await api("GET", `/api/sessions/${sid()}`); } catch (e) { return true; }
    updateLogPane("host-log", b.host_logs || []);
    updateLogPane("client-log", b.client_logs || []);
    renderLinkRows(b.link_samples || []);
    const raw = document.getElementById("bundle-data");
    if (raw) { raw.textContent = JSON.stringify(b.link_samples || []); drawRssiChart(); }
    const s = b.session || {};
    const path = document.getElementById("meta-path"); if (path) path.textContent = s.network_path || "—";
    const hc = document.getElementById("meta-hostclient"); if (hc) hc.textContent = `${s.host || "?"} → ${s.client || "?"}`;
    const pill = document.getElementById("status-pill");
    if (pill && s.status) { pill.textContent = s.status; pill.className = "pill status-" + s.status; }
    return s.status === "active";
  }

  function startLiveRefresh() {
    const el = document.getElementById("session");
    if (!el || el.dataset.status !== "active") return;
    const timer = setInterval(async () => {
      if (!(await refreshOnce())) clearInterval(timer);
    }, 8000);
  }

  function wirePasteLog() {
    const f = document.getElementById("paste-log-form"); if (!f) return;
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const content = document.getElementById("paste-content").value.trim(); if (!content) return;
      await api("POST", `/api/sessions/${sid()}/logs`, {
        source: "client", role: document.getElementById("paste-role").value,
        machine: document.getElementById("paste-machine").value || null, content });
      location.reload();
    });
  }

  function wireManualLink() {
    const f = document.getElementById("manual-link-form"); if (!f) return;
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const g = (id) => document.getElementById(id).value;
      const rssi = g("ml-rssi");
      await api("POST", `/api/sessions/${sid()}/links`, { samples: [{
        source: "client", link_type: g("ml-type"), ssid: g("ml-ssid") || null,
        bssid: (g("ml-bssid") || "").toLowerCase() || null, band: g("ml-band") || null,
        channel: g("ml-channel") || null, rssi: rssi ? Number(rssi) : null,
        link_speed: g("ml-speed") || null }] });
      location.reload();
    });
  }

  function initSessionPage() {
    applyLogFilter(); wireSyncScroll(); wireChat(); wireArtifactUpload();
    wirePasteLog(); wireManualLink(); drawRssiChart(); startLiveRefresh();
  }

  return { wireNewSessionForm, initIndexPage, initSessionPage, saveOutcome, saveNotes, stopSession,
           deleteSession, analyze, applyLogFilter };
})();

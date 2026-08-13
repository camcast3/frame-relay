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
        comparison_label: f.get("comparison_label") || null,
        apollo_app: f.get("apollo_app") || null,
        game_title: f.get("game_title") || null,
        client_role: f.get("client_role") || null,
        client_platform: f.get("client_platform") || null,
        client_version: f.get("client_version") || null,
        network_path: f.get("network_path") || null,
        requested_settings: {
          codec: f.get("codec") || null,
          resolution: f.get("resolution") || null,
          fps: f.get("fps") ? Number(f.get("fps")) : null,
          bitrate_mbps: f.get("bitrate_mbps") ? Number(f.get("bitrate_mbps")) : null,
          hdr: f.get("hdr") === "on",
        },
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

  function applyLogView() {
    const wrap = document.getElementById("wrap");
    const stack = document.getElementById("stack");
    const logs = document.querySelector(".logs");
    if (logs && stack) logs.classList.toggle("stacked", stack.checked);
    for (const id of ["host-log", "client-log"]) {
      const pre = document.getElementById(id);
      if (pre && wrap) pre.classList.toggle("nowrap", !wrap.checked);
    }
    try {
      if (wrap) localStorage.setItem("asl.wrap", wrap.checked ? "1" : "0");
      if (stack) localStorage.setItem("asl.stack", stack.checked ? "1" : "0");
    } catch (e) { /* private mode: preference just won't persist */ }
  }

  function restoreLogView() {
    try {
      const w = localStorage.getItem("asl.wrap"), s = localStorage.getItem("asl.stack");
      const wrap = document.getElementById("wrap"), stack = document.getElementById("stack");
      if (wrap && w !== null) wrap.checked = w === "1";
      if (stack && s !== null) stack.checked = s === "1";
    } catch (e) { /* ignore */ }
    applyLogView();
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
      appendTextCell(tr, s.comparison_label || "—");
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
  function renderNetTests(tests) {
    const tb = document.getElementById("nettest-tbody"); if (!tb) return;
    if (Number(tb.dataset.count || "0") === tests.length) return;   // nothing new
    tb.dataset.count = String(tests.length);
    tb.innerHTML = "";
    if (!tests.length) return;   // keep the server-rendered "how to run it" hint
    for (const t of tests) {
      const tr = document.createElement("tr");
      const jitter = t.jitter_ms != null ? t.jitter_ms + " ms" : "— ms";
      const loss = t.loss_pct != null ? t.loss_pct + "%" : "—%";
      const cells = [
        [t.tool || "—", ""], [t.direction || "—", ""], [t.bitrate_target || "—", ""],
        [t.throughput_mbps != null ? String(t.throughput_mbps) : "—", ""],
        [jitter, t.jitter_ms > 1 ? "warn" : ""], [loss, t.loss_pct > 5 ? "warn" : ""],
      ];
      for (const [txt, cls] of cells) {
        const td = document.createElement("td"); if (cls) td.className = cls;
        td.textContent = txt; tr.appendChild(td);
      }
      tb.appendChild(tr);
    }
  }

  function renderLinkSummary(samples) {
    const tb = document.getElementById("link-summary-tbody"); if (!tb) return;
    const count = document.getElementById("link-count");
    if (count) count.textContent = samples.length;
    tb.innerHTML = "";
    if (!samples.length) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 7; td.className = "muted";
      td.textContent = "No link samples yet — the collectors post them every ~10-15s.";
      tr.appendChild(td); tb.appendChild(tr); return;
    }
    // One row per source: 400 raw rows answer no question, but "was it Wi-Fi, how strong, and
    // did it roam?" is the whole point of sampling the link.
    for (const src of ["host", "client"]) {
      const rows = samples.filter(s => s.source === src);
      if (!rows.length) continue;
      const last = rows[rows.length - 1];
      const rssis = rows.map(s => s.rssi).filter(v => v != null);
      const aps = [...new Set(rows.map(s => s.bssid).filter(Boolean))];
      const nets = [...new Set(rows.map(s => s.ssid).filter(Boolean))];
      const bands = [...new Set(rows.map(s => (s.band || "") + (s.channel ? "/" + s.channel : ""))
                                   .filter(Boolean))];
      const wifi = rows.some(s => s.link_type === "wifi");

      let rssiTxt = "—", rssiCls = "";
      if (rssis.length) {
        const mn = Math.min(...rssis), mx = Math.max(...rssis);
        const avg = rssis.reduce((a, b) => a + b, 0) / rssis.length;
        rssiTxt = `${mn} / ${avg.toFixed(0)} / ${mx} dBm`;
        if (mn < -70) rssiCls = "warn";
      }
      let apTxt = aps.length ? String(aps.length) : (wifi ? "n/a" : "—");
      let apCls = "";
      if (aps.length > 1) { apTxt = aps.length + " (roamed)"; apCls = "warn"; }

      const tr = document.createElement("tr");
      const cells = [
        [src, ""], [last.link_type || "—", ""], [nets.join(", ") || "—", ""],
        [bands.join(", ") || "—", ""], [rssiTxt, rssiCls], [apTxt, apCls],
        [String(rows.length), "muted"],
      ];
      for (const [txt, cls] of cells) {
        const td = document.createElement("td"); if (cls) td.className = cls;
        td.textContent = txt; tr.appendChild(td);
      }
      tb.appendChild(tr);
    }
    // Windows 11 24H2+ withholds the BSSID unless Location Services are on, which silently
    // disables roam detection - say so rather than showing a blank AP column.
    const wifiNoBssid = samples.some(s => s.link_type === "wifi" && !s.bssid);
    if (wifiNoBssid) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 7; td.className = "muted small";
      td.textContent = "No BSSID reported for a Wi-Fi link, so AP-roam detection is off. "
        + "On Windows 11 enable Settings > Privacy & security > Location on that machine.";
      tr.appendChild(td); tb.appendChild(tr);
    }
  }

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

  function text(id, value) {
    const el = document.getElementById(id); if (el) el.textContent = value;
  }

  function yn(value) { return value === true ? "yes" : (value === false ? "no" : "—"); }

  function renderStreamEvidence(s) {
    const req = s.requested_settings || {}, hd = s.hdr_details || {};
    text("identity-comparison", s.comparison_label || "—");
    text("identity-app", s.apollo_app || "—");
    text("identity-game", s.game_title || "—");
    text("identity-role", s.client_role || "—");
    text("identity-platform", s.client_platform || "—");
    text("identity-version", s.client_version || "—");
    text("req-codec", req.codec || "—"); text("eff-codec", s.codec || "—");
    text("req-resolution", req.resolution || "—"); text("eff-resolution", s.resolution || "—");
    text("req-fps", req.fps ?? "—"); text("eff-fps", s.fps ?? "—");
    text("req-bitrate", req.bitrate_mbps == null ? "—" : `${req.bitrate_mbps} Mbps`);
    text("eff-bitrate", s.bitrate_mbps == null ? "—" : `${s.bitrate_mbps} Mbps`);
    text("req-hdr", yn(req.hdr)); text("eff-hdr", s.hdr ? "yes" : "no");
    text("hdr-requested", yn(hd.requested)); text("hdr-host-display", yn(hd.host_display_hdr));
    text("hdr-encoded", yn(hd.encoded_hdr));
    text("hdr-color", `${hd.color_primaries || "—"} / ${hd.transfer_function || "—"} / ${hd.bit_depth ? hd.bit_depth + "-bit" : "—"}`);
    text("hdr-client", `${hd.client_decoder || "—"} / ${hd.client_renderer || "—"}`);
    text("hdr-client-display", yn(hd.client_display_hdr));
    text("hdr-tone", hd.tone_mapping || "—"); text("hdr-status", hd.status || "unknown");
    const evidence = Array.isArray(hd.evidence) ? hd.evidence.join("; ") : (hd.evidence || "—");
    text("hdr-evidence", `${evidence}${hd.confidence != null ? " · " + hd.confidence + " confidence" : ""}`);
    text("meta-codec", `${s.codec || "—"}${s.hdr ? " · HDR" : ""}`);
    text("meta-video", `${s.resolution || "—"} @ ${s.fps || "—"}fps · ${s.bitrate_mbps || "—"} Mbps`);
  }

  function displayState(value) {
    return value === true || value === 1 ? "yes" : (
      value === false || value === 0 ? "no" : "unknown"
    );
  }

  function renderDisplayValidation(result, samples) {
    if (!result) return;
    const hasSamples = (samples || []).length > 0;
    const empty = document.getElementById("display-empty");
    const content = document.getElementById("display-content");
    if (empty) empty.hidden = hasSamples;
    if (content) content.hidden = !hasSamples;
    const checks = result.checks || {}, expected = result.expected || {}, actual = result.actual || {};
    const status = document.getElementById("display-status");
    if (status) {
      status.textContent = result.status || "partial";
      status.className = "pill display-" + (result.status || "partial");
    }
    text("display-name", result.display_name || "unknown");
    text("display-virtual", displayState(checks.virtual_display_active));
    text("display-resolution", `${actual.resolution || "—"} / expected ${expected.resolution || "—"}`);
    text("display-refresh", `${actual.refresh_hz ?? "—"} Hz / expected ${expected.refresh_hz ?? "—"} Hz`);
    text("display-hdr", `${displayState(actual.hdr)} / expected ${displayState(expected.hdr)}`);
    text("display-only", displayState(checks.only_active_display));
    text("display-restored", displayState(checks.topology_restored_after));
    text("display-mode-summary", `Resolution ${displayState(checks.resolution_matches)} · refresh ${displayState(checks.refresh_matches)} · HDR ${displayState(checks.hdr_matches)}`);
    text("display-count", String((samples || []).length));

    const tb = document.getElementById("display-tbody"); if (!tb) return;
    tb.innerHTML = "";
    for (const d of samples || []) {
      const tr = document.createElement("tr");
      const cells = [
        [`${d.phase || "—"} ${(d.sampled_at || "").substring(11, 19)}`, "mono"],
        [d.friendly_name || d.source_name || "unknown", ""],
        [displayState(d.is_virtual), ""], [displayState(d.primary), ""],
        [`${d.width ?? "—"}x${d.height ?? "—"} @ ${d.refresh_hz ?? "—"} Hz`, ""],
        [`${displayState(d.hdr_enabled)}${d.bits_per_channel ? " · " + d.bits_per_channel + "-bit" : ""}`, ""],
        [`${d.adapter_id || "—"} / ${d.source_id ?? "—"} → ${d.target_id ?? "—"}`, "mono"],
      ];
      for (const [value, cls] of cells) {
        const td = document.createElement("td"); td.textContent = value;
        if (cls) td.className = cls; tr.appendChild(td);
      }
      tb.appendChild(tr);
    }
  }

  async function refreshOnce() {
    let b;
    try { b = await api("GET", `/api/sessions/${sid()}`); } catch (e) { return true; }
    updateLogPane("host-log", b.host_logs || []);
    updateLogPane("client-log", b.client_logs || []);
    renderLinkRows(b.link_samples || []);
    renderLinkSummary(b.link_samples || []);
    renderNetTests(b.net_tests || []);
    renderDisplayValidation(b.display_validation, b.display_samples || []);
    const raw = document.getElementById("bundle-data");
    if (raw) { raw.textContent = JSON.stringify(b.link_samples || []); drawRssiChart(); }
    const s = b.session || {};
    const path = document.getElementById("meta-path"); if (path) path.textContent = s.network_path || "—";
    const hc = document.getElementById("meta-hostclient"); if (hc) hc.textContent = `${s.host || "?"} → ${s.client || "?"}`;
    renderStreamEvidence(s);
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

  function field(id) { return document.getElementById(id)?.value ?? ""; }
  function nullableNumber(id) { const value = field(id); return value === "" ? null : Number(value); }
  function nullableBool(id) { const value = field(id); return value === "" ? null : value === "true"; }

  function wireEvidenceForm() {
    const f = document.getElementById("evidence-form"); if (!f) return;
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = {
        comparison_label: field("ev-comparison") || null,
        apollo_app: field("ev-app") || null,
        game_title: field("ev-game") || null,
        client_role: field("ev-role") || null,
        client_platform: field("ev-platform") || null,
        client_version: field("ev-version") || null,
        codec: field("ev-eff-codec") || null,
        resolution: field("ev-eff-resolution") || null,
        fps: nullableNumber("ev-eff-fps"),
        bitrate_mbps: nullableNumber("ev-eff-bitrate"),
        hdr: nullableBool("ev-eff-hdr"),
        requested_settings: {
          codec: field("ev-req-codec") || null,
          resolution: field("ev-req-resolution") || null,
          fps: nullableNumber("ev-req-fps"),
          bitrate_mbps: nullableNumber("ev-req-bitrate"),
          hdr: nullableBool("ev-req-hdr"),
        },
        hdr_details: {
          requested: nullableBool("ev-req-hdr"),
          host_display_hdr: nullableBool("ev-hdr-host"),
          encoded_hdr: nullableBool("ev-hdr-encoded"),
          color_primaries: field("ev-primaries") || null,
          transfer_function: field("ev-transfer") || null,
          bit_depth: nullableNumber("ev-depth"),
          client_decoder: field("ev-decoder") || null,
          client_renderer: field("ev-renderer") || null,
          client_display_hdr: nullableBool("ev-hdr-client-display"),
          tone_mapping: field("ev-tone") || null,
          status: field("ev-hdr-status") || null,
          evidence: ["operator"],
          confidence: 1.0,
        },
        visual_assessment: {
          rating: nullableNumber("ev-rating"),
          brightness: field("ev-brightness") || null,
          black_levels: field("ev-blacks") || null,
          colors: field("ev-colors") || null,
          notes: field("ev-visual-notes") || null,
        },
      };
      await api("PATCH", `/api/sessions/${sid()}`, payload);
      location.reload();
    });
  }

  function initSessionPage() {
    restoreLogView(); applyLogFilter(); wireSyncScroll(); wireChat(); wireArtifactUpload();
    wirePasteLog(); wireManualLink(); wireEvidenceForm(); drawRssiChart(); startLiveRefresh();
    const raw = document.getElementById("bundle-data");
    if (raw) { try { renderLinkSummary(JSON.parse(raw.textContent) || []); } catch (e) {} }
  }

  return { wireNewSessionForm, initIndexPage, initSessionPage, saveOutcome, saveNotes, stopSession,
           deleteSession, analyze, applyLogFilter, applyLogView };
})();

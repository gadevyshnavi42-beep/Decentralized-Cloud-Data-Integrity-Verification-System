const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtSize = (b) => (b < 1024 ? b + " B" : b < 1048576 ? (b / 1024).toFixed(1) + " KB" : (b / 1048576).toFixed(2) + " MB");
const badge = (s) => `<span class="badge ${s === "Verified" ? "bg-success" : "bg-danger"}">${esc(s)}</span>`;

function toast(msg, type = "success") {
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${type} border-0 show`;
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(msg)}</div><button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  let d = {};
  try { d = await r.json(); } catch (e) { /* non-JSON response */ }
  if (r.status === 401 && !location.pathname.match(/login|register/)) { location.href = "/login"; }
  if (!r.ok) throw new Error(d.error || "Request failed");
  return d;
}
const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const setBusy = (btn, busy, label) => { btn.disabled = busy; if (label) btn.textContent = busy ? "Please wait…" : label; };

const pages = {
  register() {
    $("#registerForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      if ($("#password").value !== $("#confirm").value) return toast("Passwords do not match.", "danger");
      try {
        const d = await post("/api/register", { username: $("#username").value, email: $("#email").value,
          password: $("#password").value, confirm_password: $("#confirm").value });
        toast(d.message); setTimeout(() => (location.href = "/login"), 1000);
      } catch (err) { toast(err.message, "danger"); }
    });
  },

  login() {
    $("#loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await post("/api/login", { email: $("#email").value, password: $("#password").value });
        location.href = "/dashboard";
      } catch (err) { toast(err.message, "danger"); }
    });
  },

  async dashboard() {
    try {
      const d = await api("/api/dashboard");
      ["total_files", "total_verifications", "verified", "failed"].forEach((k) => ($("#" + k).textContent = d[k]));
      const t = d.verified + d.failed;
      $("#barOk").style.width = t ? (d.verified / t) * 100 + "%" : "0";
      $("#barBad").style.width = t ? (d.failed / t) * 100 + "%" : "0";
      $("#recent").innerHTML = d.recent.length
        ? d.recent.map((r) => `<tr><td>${esc(r.filename)}</td><td>${esc(r.verified_at)}</td><td>${badge(r.verification_status)}</td></tr>`).join("")
        : '<tr><td colspan="3" class="text-muted">No verifications yet.</td></tr>';
    } catch (err) { toast(err.message, "danger"); }
  },

  upload() {
    const input = $("#fileInput"), zone = $("#dropzone"), btn = $("#uploadBtn");
    const show = () => {
      const f = input.files[0];
      if (!f) return;
      $("#fName").textContent = f.name; $("#fSize").textContent = "(" + fmtSize(f.size) + ")";
      $("#fileInfo").classList.remove("d-none"); btn.disabled = false; $("#uploadStatus").innerHTML = "";
    };
    $("#chooseBtn").onclick = () => input.click();
    input.onchange = show;
    ["dragover", "dragenter"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("over"); }));
    zone.addEventListener("drop", (e) => { input.files = e.dataTransfer.files; show(); });

    btn.onclick = () => {
      const f = input.files[0];
      if (!f) return;
      if (f.size > 16 * 1024 * 1024) return toast("File too large (max 16 MB).", "danger");
      const fd = new FormData(); fd.append("file", f);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      $("#progWrap").classList.remove("d-none"); btn.disabled = true;
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) $("#progBar").style.width = (e.loaded / e.total) * 100 + "%"; };
      xhr.onload = () => {
        let d = {}; try { d = JSON.parse(xhr.responseText); } catch (e) { /* ignore */ }
        if (xhr.status === 201) {
          toast(d.message);
          $("#uploadStatus").innerHTML = `<div class="alert alert-success mb-0"><b>Upload complete.</b><div class="small mt-2">SHA-256:</div><code class="hash">${esc(d.sha256_hash)}</code></div>`;
        } else { toast(d.error || "Upload failed.", "danger"); btn.disabled = false; }
        $("#progWrap").classList.add("d-none"); $("#progBar").style.width = "0";
      };
      xhr.onerror = () => { toast("Network error.", "danger"); btn.disabled = false; };
      xhr.send(fd);
    };
  },

  async files() {
    const body = $("#filesBody");
    async function load() {
      try {
        const { files } = await api("/api/files");
        body.innerHTML = files.length ? files.map((f) => `<tr>
          <td>${esc(f.filename)}</td><td>${esc(f.uploaded_at)}</td><td>${fmtSize(f.file_size)}</td>
          <td><code class="hash">${esc(f.sha256_hash)}</code></td>
          <td class="text-nowrap">
            <a class="btn btn-sm btn-outline-primary" title="Download" href="/api/files/${f.id}/download"><i class="bi bi-download"></i></a>
            <a class="btn btn-sm btn-outline-success" title="Verify" href="/verify?file=${f.id}"><i class="bi bi-shield-check"></i></a>
            <button class="btn btn-sm btn-outline-danger" title="Delete" data-del="${f.id}"><i class="bi bi-trash"></i></button>
          </td></tr>`).join("") : '<tr><td colspan="5" class="text-muted">No files uploaded yet.</td></tr>';
      } catch (err) { toast(err.message, "danger"); }
    }
    body.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-del]");
      if (!b || !confirm("Delete this file permanently?")) return;
      try { toast((await api("/api/files/" + b.dataset.del, { method: "DELETE" })).message); load(); }
      catch (err) { toast(err.message, "danger"); }
    });
    load();
  },

  async verify() {
    const sel = $("#fileSelect"), spin = $("#spinner"), res = $("#result");
    const want = new URLSearchParams(location.search).get("file");
    try {
      const { files } = await api("/api/files");
      sel.innerHTML = files.length ? files.map((f) => `<option value="${f.id}" ${String(f.id) === want ? "selected" : ""}>${esc(f.filename)}</option>`).join("")
                                   : "<option value=''>No files uploaded</option>";
    } catch (err) { toast(err.message, "danger"); }

    const hashRow = (label, h) => `<div class="small text-muted mt-2">${label}</div><code class="hash">${esc(h)}</code>`;
    const run = async (fn) => {
      if (!sel.value) return toast("Upload a file first.", "danger");
      spin.classList.remove("d-none"); $("#verifyBtn").disabled = $("#decBtn").disabled = true;
      try { res.innerHTML = fn(await runRequest.current()); } catch (err) { toast(err.message, "danger"); }
      spin.classList.add("d-none"); $("#verifyBtn").disabled = $("#decBtn").disabled = false;
    };
    const runRequest = { current: null };

    $("#verifyBtn").onclick = () => {
      runRequest.current = () => {
        const fd = new FormData(); const f = $("#cmpFile").files[0]; if (f) fd.append("file", f);
        return api("/api/verify/" + sel.value, { method: "POST", body: fd });
      };
      run((d) => {
        const ok = d.status === "Verified";
        return `<div class="alert alert-${ok ? "success" : "danger"}"><i class="bi bi-${ok ? "check-circle" : "x-octagon"}"></i>
          <b>${ok ? "Integrity Verified" : "Integrity Failed"}</b>: ${ok ? "File hashes match." : "File hashes do not match."}</div>
          <div class="small text-muted">Checked: ${esc(d.source)} · ${esc(d.filename)}</div>
          ${hashRow("Original hash (stored)", d.original_hash)}${hashRow("Calculated hash", d.calculated_hash)}
          <div class="small text-muted mt-3">Verified at ${esc(d.verified_at)}</div>`;
      });
    };

    $("#decBtn").onclick = () => {
      runRequest.current = () => api("/api/decentralized-verify/" + sel.value, { method: "POST" });
      run((d) => `<div class="badge text-bg-warning mb-2">SIMULATED decentralized network — not a real blockchain</div>
        <h5>${esc(d.filename)}</h5>
        ${d.nodes.map((n) => `<div class="node-row ${n.agrees ? "node-ok" : "node-bad"} p-2 mb-2">
          <b>${esc(n.node)}</b> — ${n.agrees ? "✅ hash matches" : "❌ mismatch"}<br><code class="hash">${esc(n.hash)}</code></div>`).join("")}
        <div class="alert alert-${d.consensus ? "success" : "danger"} mt-3 mb-1"><b>${d.agreeing} of ${d.total} nodes agree</b> with the stored hash.<br>${esc(d.message)}</div>
        <div class="small text-muted">Verified at ${esc(d.verified_at)}</div>`);
    };
  },

  async history() {
    try {
      const { history } = await api("/api/history");
      $("#historyBody").innerHTML = history.length
        ? history.map((h) => `<tr><td>${esc(h.filename)}</td><td>${esc(h.verified_at)}</td><td>${badge(h.verification_status)}</td></tr>`).join("")
        : '<tr><td colspan="3" class="text-muted">No verification history yet.</td></tr>';
    } catch (err) { toast(err.message, "danger"); }
  },
};

document.addEventListener("DOMContentLoaded", () => {
  const out = $("#logoutBtn");
  if (out) out.onclick = async () => { await post("/api/logout", {}); location.href = "/"; };
  const init = pages[document.body.dataset.page];
  if (init) init();
});

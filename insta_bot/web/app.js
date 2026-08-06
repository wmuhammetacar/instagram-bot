const $ = (sel) => document.querySelector(sel);

let statusData = null;

function toast(msg, isError = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = msg;
  $("#toast").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtTime(iso) {
  if (!iso) return "—";
  return String(iso).slice(11, 19);
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#${btn.dataset.tab}`).classList.add("active");
    refresh(btn.dataset.tab);
  });
});

function refresh(tab) {
  if (tab === "overview" || !tab) loadOverview();
  if (tab === "targets") loadTargets();
  if (tab === "actions") loadActions();
  if (tab === "tasks") loadTasks();
  if (tab === "report") loadReport();
}

async function loadOverview() {
  try {
    statusData = await api("/api/status");
  } catch (e) {
    toast("Durum alınamadı: " + e.message, true);
    return;
  }
  $("#clock").textContent = statusData.date + " " + statusData.time;
  const t = statusData.targets;
  $("#global-stats").innerHTML = [
    ["Hedef (Bekliyor)", t.pending],
    ["Hedef (İşlendi)", t.processed],
    ["Kara Liste", t.blacklisted],
    ["Toplam Hedef", t.total],
  ].map(([l, n]) => `<div class="stat"><div class="num">${n}</div><div class="lbl">${l}</div></div>`).join("");

  $("#account-cards").innerHTML = statusData.accounts.map((acc) => {
    const rt = acc.runtime;
    const statusClass = acc.needs_challenge ? "challenge"
      : rt.status === "running" ? "running"
      : rt.message.startsWith("hata") ? "error" : "idle";
    const statusLabel = acc.needs_challenge ? "Challenge"
      : rt.status === "running" ? "Çalışıyor"
      : rt.message || "Beklemede";
    const cooldowns = Object.keys(acc.cooldowns).length
      ? `<span class="badge cooldown" title="${esc(Object.keys(acc.cooldowns).join(", "))}">KISIT</span>` : "";
    const meters = ["follows", "likes", "comments", "dms", "posts"].map((k) => {
      const used = acc.today[k] || 0;
      const cap = (acc.limits && acc.limits[k]) || 0;
      const pct = cap ? Math.min(100, Math.round((used / cap) * 100)) : 0;
      const cls = pct >= 100 ? "full" : pct >= 75 ? "warn" : "ok";
      return `<div class="meter">
        <div class="row"><span class="lbl">${k}</span><span>${used} / ${cap}</span></div>
        <div class="bar ${cls}"><i style="width:${pct}%"></i></div>
      </div>`;
    }).join("");
    return `<div class="card">
      <div class="card-head">
        <h2>${esc(acc.name)} <span class="muted">@${esc(acc.username)}</span></h2>
        <span>
          <span class="badge ${statusClass}">${esc(statusLabel)}</span>
          ${cooldowns}
        </span>
      </div>
      ${meters}
      <div class="muted">Son giriş: ${esc(acc.last_login || "—")} ${acc.proxy ? "· Proxy ✓" : ""} ${acc.windows.length ? `· Pencere: ${acc.windows.join(",")}` : ""}</div>
      <div class="card-actions">
        <button class="btn ghost small" data-login="${esc(acc.name)}">Giriş</button>
        <button class="btn small" data-engage="${esc(acc.name)}">Engajman</button>
        <button class="btn ghost small" data-dm="${esc(acc.name)}">DM</button>
      </div>
    </div>`;
  }).join("");

  if (document.querySelector("[data-tab='overview']").classList.contains("active")) {
    setTimeout(loadOverview, 5000);
  }
}

document.addEventListener("click", async (e) => {
  const login = e.target.dataset.login;
  if (login) {
    try {
      await api(`/api/account/${login}/login`, { method: "POST", body: "{}" });
      toast(login + ": giriş başlatıldı");
    } catch (err) { toast(err.message, true); }
    return;
  }
  if (e.target.dataset.engage) openEngage(e.target.dataset.engage);
  if (e.target.dataset.dm) openDm(e.target.dataset.dm);
});

function openEngage(account) {
  $("#modal-title").textContent = `Engajman — ${account}`;
  $("#modal-body").innerHTML = `
    <div class="field"><label>Hashtagler (virgülle)</label>
      <input id="m-hashtags" class="input" placeholder="python, coding"></div>
    <div class="field"><label>Hedef hesap(lar) (virgülle)</label>
      <input id="m-accounts" class="input" placeholder="rakip1, rakip2"></div>
    <div class="field"><label>Bütçe (aksiyon sayısı)</label>
      <input id="m-budget" class="input" type="number" value="15"></div>
    <div class="check-row">
      <label><input type="checkbox" id="m-like" checked> Beğeni</label>
      <label><input type="checkbox" id="m-comment"> Yorum</label>
      <label><input type="checkbox" id="m-dry"> Kuru çalışma</label>
    </div>`;
  $("#modal").classList.remove("hidden");
  $("#modal-ok").onclick = async () => {
    try {
      await api("/api/engage", { method: "POST", body: JSON.stringify({
        account,
        hashtags: $("#m-hashtags").value.split(",").map((s) => s.trim()).filter(Boolean),
        competitors: $("#m-accounts").value.split(",").map((s) => s.trim()).filter(Boolean),
        budget: parseInt($("#m-budget").value) || null,
        like: $("#m-like").checked, comment: $("#m-comment").checked,
        dry_run: $("#m-dry").checked,
      })});
      toast(account + ": engajman kuyruğa alındı");
      $("#modal").classList.add("hidden");
    } catch (err) { toast(err.message, true); }
  };
}

function openDm(account) {
  $("#modal-title").textContent = `DM — ${account}`;
  $("#modal-body").innerHTML = `
    <div class="field"><label>Kullanıcı adları (virgülle veya boşlukla)</label>
      <input id="m-users" class="input" placeholder="kullanici1, kullanici2"></div>
    <div class="check-row"><label><input type="checkbox" id="m-dry"> Kuru çalışma</label></div>`;
  $("#modal").classList.remove("hidden");
  $("#modal-ok").onclick = async () => {
    try {
      await api("/api/dm", { method: "POST", body: JSON.stringify({
        account,
        usernames: $("#m-users").value.split(/[\s,]+/).filter(Boolean),
        dry_run: $("#m-dry").checked,
      })});
      toast(account + ": DM kuyruğa alındı");
      $("#modal").classList.add("hidden");
    } catch (err) { toast(err.message, true); }
  };
}

$("#modal-close").onclick = () => $("#modal").classList.add("hidden");

async function loadTargets() {
  try {
    const q = new URLSearchParams({ limit: 200 });
    if ($("#t-status").value) q.set("status", $("#t-status").value);
    const targets = await api("/api/targets?" + q);
    const filter = ($("#t-filter").value || "").toLowerCase();
    const rows = targets.filter((t) =>
      !filter || (t.username || "").toLowerCase().includes(filter) || (t.bio || "").toLowerCase().includes(filter));
    $("#targets-table").innerHTML = `<thead><tr>
      <th>Kullanıcı</th><th>Puan</th><th>Takipçi</th><th>Medya</th><th>Biyo</th><th>Kaynak</th><th>Durum</th><th></th>
    </tr></thead><tbody>${rows.map((t) => `<tr>
      <td>${esc(t.username)}</td>
      <td>${t.score}</td>
      <td>${t.followers}</td>
      <td>${t.media_count}</td>
      <td class="bio" title="${esc(t.bio)}">${esc((t.bio || "").slice(0, 60))}</td>
      <td>${esc(t.source || "—")}</td>
      <td><span class="status ${esc(t.status)}">${esc(t.status)}</span></td>
      <td><button class="btn danger small" data-bl="${esc(t.account)}|${esc(t.pk)}">Kara</button></td>
    </tr>`).join("")}</tbody>`;
  } catch (e) { toast("Hedefler alınamadı: " + e.message, true); }
}

document.addEventListener("click", async (e) => {
  const bl = e.target.dataset.bl;
  if (!bl) return;
  const [account, pk] = bl.split("|");
  try {
    await api("/api/targets/blacklist", { method: "POST", body: JSON.stringify({ account, pk }) });
    toast("Kara listeye alındı");
    loadTargets();
  } catch (err) { toast(err.message, true); }
});

$("#t-refresh").onclick = loadTargets;
$("#t-status").onchange = loadTargets;
$("#t-filter").oninput = () => { /* live filter on next refresh is fine; re-render on input */ loadTargets(); };
$("#t-clear").onclick = async () => {
  try {
    await api("/api/targets/clear", { method: "POST", body: JSON.stringify({ status: "processed" }) });
    toast("İşlenen hedefler temizlendi");
    loadTargets();
  } catch (err) { toast(err.message, true); }
};

async function loadActions() {
  try {
    const acts = await api("/api/actions?limit=100");
    $("#actions-table").innerHTML = `<thead><tr>
      <th>Saat</th><th>Hesap</th><th>Aksiyon</th><th>Hedef</th><th>Durum</th><th>Hata</th>
    </tr></thead><tbody>${acts.map((a) => `<tr>
      <td>${esc(fmtTime(a.created_at))}</td>
      <td>${esc(a.account)}</td>
      <td>${esc(a.action_type)}</td>
      <td>${esc(a.target || "—")}</td>
      <td><span class="status ${esc(a.status)}">${esc(a.status)}</span></td>
      <td class="bio" title="${esc(a.error)}">${esc((a.error || "").slice(0, 80))}</td>
    </tr>`).join("")}</tbody>`;
  } catch (e) { toast("Aksiyonlar alınamadı: " + e.message, true); }
}
$("#a-refresh").onclick = loadActions;

async function loadTasks() {
  try {
    const tasks = await api("/api/tasks");
    $("#tasks-table").innerHTML = `<thead><tr>
      <th>Ad</th><th>Hesap</th><th>Aksiyon</th><th>Program</th><th>Sonraki</th><th>Son</th><th>Durum</th><th></th>
    </tr></thead><tbody>${tasks.map((t) => `<tr>
      <td>${esc(t.name)}</td>
      <td>${esc(t.account)}</td>
      <td>${esc(t.action)}</td>
      <td class="mono">${esc(t.schedule || "{}")}</td>
      <td>${esc(t.next_run || "—")}</td>
      <td>${esc(t.last_run || "—")}</td>
      <td><span class="status ${t.enabled ? "processed" : "skipped"}">${t.enabled ? "aktif" : "pasif"}</span></td>
      <td>
        <button class="btn ghost small" data-toggle="${t.id}">${t.enabled ? "Durdur" : "Başlat"}</button>
        <button class="btn danger small" data-del="${t.id}">Sil</button>
      </td>
    </tr>`).join("")}</tbody>`;
    const accSel = $("#tk-account");
    const data = statusData || await api("/api/status");
    accSel.innerHTML = data.accounts.map((a) => `<option value="${esc(a.name)}">${esc(a.name)}</option>`).join("");
  } catch (e) { toast("Görevler alınamadı: " + e.message, true); }
}

document.addEventListener("click", async (e) => {
  const toggle = e.target.dataset.toggle;
  const del = e.target.dataset.del;
  try {
    if (toggle) { await api(`/api/tasks/${toggle}/toggle`, { method: "POST", body: "{}" }); loadTasks(); }
    if (del) { await api(`/api/tasks/${del}`, { method: "DELETE" }); loadTasks(); }
  } catch (err) { toast(err.message, true); }
});

$("#tk-refresh").onclick = loadTasks;
$("#tk-add").onclick = async () => {
  let schedule = {};
  try { schedule = JSON.parse($("#tk-schedule").value || "{}"); }
  catch { toast("Program JSON geçersiz", true); return; }
  try {
    await api("/api/tasks", { method: "POST", body: JSON.stringify({
      name: $("#tk-name").value || "gorev_" + Date.now(),
      account: $("#tk-account").value,
      action: $("#tk-action").value,
      schedule,
    })});
    toast("Görev eklendi");
    loadTasks();
  } catch (err) { toast(err.message, true); }
};

async function loadReport() {
  try {
    const q = new URLSearchParams();
    if ($("#r-date").value) q.set("date", $("#r-date").value);
    const rep = await api("/api/report?" + q);
    const typeLabels = { follows: "Takip", likes: "Beğeni", comments: "Yorum", dms: "DM", posts: "Paylaşım", errors: "Hata" };
    const cards = Object.entries(rep.accounts).map(([name, d]) => {
      const rows = Object.keys(typeLabels).map((k) => {
        const cap = d.limits ? d.limits[k] : null;
        const used = d[k] || 0;
        return `<tr><td>${typeLabels[k]}</td><td>${used}</td><td>${cap ?? "—"}</td>
          <td>${cap ? Math.round((used / cap) * 100) + "%" : "—"}</td></tr>`;
      }).join("");
      return `<div class="table-wrap ratio-table"><table><thead><tr>
        <th>${esc(name)}</th><th>Kullanım</th><th>Limit</th><th>Oran</th>
      </tr></thead><tbody>${rows}</tbody></table></div>`;
    }).join("");
    $("#report-body").innerHTML = `<h3>Özet — ${rep.date}</h3>` + cards;
  } catch (e) { toast("Rapor alınamadı: " + e.message, true); }
}
$("#r-refresh").onclick = loadReport;

refresh("overview");

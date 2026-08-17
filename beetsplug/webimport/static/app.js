// beets-webimport frontend. No build step / framework -- plain fetch +
// DOM. Kept intentionally simple; see README "Known simplifications".

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

// -- tabs --------------------------------------------------------------
$$("#tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("#tabs button").forEach((b) => b.classList.remove("active"));
    $$(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    $(`#tab-${btn.dataset.tab}`).classList.add("active");
    refreshTab(btn.dataset.tab);
  });
});

function refreshTab(tab) {
  if (tab === "inbox") loadInbox();
  if (tab === "undo") loadUndo();
  if (tab === "library") loadLibrary();
  if (tab === "tags") loadTags();
}

// -- modal helper --------------------------------------------------------
function openModal(contentEl) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const modal = document.createElement("div");
  modal.className = "modal";
  modal.appendChild(contentEl);
  backdrop.appendChild(modal);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  $("#modal-root").appendChild(backdrop);
  return backdrop;
}

// long-press -> menu, as the touch-friendly equivalent of drag-and-drop
// for actions like "move to bin" / "apply tag" / "assign library".
function attachLongPress(el, buildMenuItems) {
  let timer;
  const start = (x, y) => {
    timer = setTimeout(() => showLongPressMenu(x, y, buildMenuItems()), 450);
  };
  const cancel = () => clearTimeout(timer);
  el.addEventListener("touchstart", (e) => {
    const t = e.touches[0];
    start(t.clientX, t.clientY);
  });
  el.addEventListener("touchend", cancel);
  el.addEventListener("touchmove", cancel);
  el.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    showLongPressMenu(e.clientX, e.clientY, buildMenuItems());
  });
}

function showLongPressMenu(x, y, items) {
  $$(".long-press-menu").forEach((m) => m.remove());
  const menu = document.createElement("div");
  menu.className = "long-press-menu";
  menu.style.left = `${Math.min(x, window.innerWidth - 180)}px`;
  menu.style.top = `${Math.min(y, window.innerHeight - items.length * 36 - 20)}px`;
  items.forEach(({ label, onClick }) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.addEventListener("click", () => {
      menu.remove();
      onClick();
    });
    menu.appendChild(b);
  });
  document.body.appendChild(menu);
  setTimeout(() => {
    document.addEventListener("click", () => menu.remove(), { once: true });
  }, 0);
}

// ===================== INBOX / REVIEW ===================================
async function loadInbox() {
  const data = await api("/api/inbox");

  const dirsEl = $("#inbox-dirs");
  dirsEl.innerHTML = "";
  if (data.inbox_dirs.length === 0) {
    dirsEl.innerHTML = '<p class="timer">Inbox is empty.</p>';
  }
  data.inbox_dirs.forEach((path) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="path">${path}</div>
      <div class="row">
        <button data-start>Start import</button>
      </div>`;
    card.querySelector("[data-start]").addEventListener("click", async () => {
      await api("/api/inbox/start", {
        method: "POST",
        body: JSON.stringify({ paths: [path] }),
      });
      loadInbox();
    });
    dirsEl.appendChild(card);
  });

  const pendingEl = $("#pending-reviews");
  pendingEl.innerHTML = "";
  data.pending_review.forEach((pr) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="path">${pr.path}</div>
      <div>${pr.kind === "duplicate" ? "Possible duplicate" : "Awaiting candidate review"}</div>
      <button data-review>Review</button>`;
    card.querySelector("[data-review]").addEventListener("click", () => openReview(pr));
    pendingEl.appendChild(card);
  });
}

async function openReview(pr) {
  if (pr.kind === "duplicate") return openDuplicateReview(pr);

  const container = document.createElement("div");
  container.innerHTML = `<h3>${pr.path}</h3>`;
  const list = document.createElement("div");
  container.appendChild(list);

  let focusedIndex = null;

  function renderCandidates() {
    list.innerHTML = "";
    pr.payload.candidates.forEach((c, i) => {
      const div = document.createElement("div");
      div.className = "candidate" + (focusedIndex === i ? " focused" : "");
      const artistAlbum = c.album ? `${c.artist} – ${c.album}` : `${c.artist} – ${c.title}`;
      div.innerHTML = `
        <div>${artistAlbum} ${c.year ? `(${c.year})` : ""}</div>
        <div class="dist">distance ${c.distance} · ${c.data_source || "?"}</div>
        <div class="art-compare" data-art></div>
        <div class="row">
          <button data-select>Select</button>
        </div>`;
      div.addEventListener("click", () => {
        if (focusedIndex !== i) {
          focusedIndex = i;
          renderCandidates();
          loadArtCompare(div, pr, c);
        }
      });
      div.querySelector("[data-select]").addEventListener("click", async (e) => {
        e.stopPropagation();
        await decide(pr.task_id, { action: "select", index: i });
        backdrop.remove();
        loadInbox();
      });
      list.appendChild(div);
    });
  }

  renderCandidates();
  if (pr.payload.candidates.length) {
    focusedIndex = 0;
    renderCandidates();
    loadArtCompare($(".candidate", list), pr, pr.payload.candidates[0]);
  }

  const idRow = document.createElement("div");
  idRow.className = "row";
  idRow.innerHTML = `
    <input type="text" placeholder="Paste MusicBrainz ID or URL" style="flex:1" data-mbid />
    <button data-use-id>Use ID</button>
    <button class="secondary" data-asis>Use as-is</button>
    <button class="danger" data-skip>Skip</button>`;
  idRow.querySelector("[data-use-id]").addEventListener("click", async () => {
    const raw = idRow.querySelector("[data-mbid]").value.trim();
    const id = raw.split("/").pop();
    if (!id) return;
    await decide(pr.task_id, { action: "search_id", search_id: id });
    backdrop.remove();
    loadInbox();
  });
  idRow.querySelector("[data-asis]").addEventListener("click", async () => {
    await decide(pr.task_id, { action: "asis" });
    backdrop.remove();
    loadInbox();
  });
  idRow.querySelector("[data-skip]").addEventListener("click", async () => {
    await decide(pr.task_id, { action: "skip" });
    backdrop.remove();
    loadInbox();
  });
  container.appendChild(idRow);

  var backdrop = openModal(container);
}

async function loadArtCompare(candidateEl, pr, candidate) {
  const holder = candidateEl.querySelector("[data-art]");
  holder.innerHTML = '<span class="timer">Resolving art…</span>';
  try {
    const result = await api("/api/coverart/resolve", {
      method: "POST",
      body: JSON.stringify({
        item_dir: pr.path,
        release_mbid: candidate.album_id,
        release_group_mbid: null,
      }),
    });
    holder.innerHTML = `
      ${result.source_url ? `<img src="${result.source_url}" alt="source" />` : "<span>no source art</span>"}
      ${result.resolved_url ? `<img src="${result.resolved_url}" alt="resolved" />` : "<span>no resolved art</span>"}
      <span class="art-badge ${result.match ? "match" : "mismatch"}">${result.match ? "match" : "differs"}</span>`;
  } catch {
    holder.innerHTML = '<span class="timer">art preview unavailable</span>';
  }
}

async function openDuplicateReview(pr) {
  const container = document.createElement("div");
  container.innerHTML = `
    <h3>Possible duplicate — ${pr.path}</h3>
    <ul>${pr.payload.duplicates.map((d) => `<li>${d.album}</li>`).join("")}</ul>
    <div class="row">
      <button data-keep-both>Keep both</button>
      <button class="secondary" data-remove-old>Replace existing</button>
      <button class="danger" data-skip>Skip new</button>
    </div>`;
  container.querySelector("[data-keep-both]").addEventListener("click", async () => {
    await decide(pr.task_id, { action: "keep_both" });
    backdrop.remove();
    loadInbox();
  });
  container.querySelector("[data-remove-old]").addEventListener("click", async () => {
    await decide(pr.task_id, { action: "remove_old" });
    backdrop.remove();
    loadInbox();
  });
  container.querySelector("[data-skip]").addEventListener("click", async () => {
    await decide(pr.task_id, { action: "skip" });
    backdrop.remove();
    loadInbox();
  });
  var backdrop = openModal(container);
}

function decide(taskId, decision) {
  return api(`/api/review/${taskId}/decide`, {
    method: "POST",
    body: JSON.stringify(decision),
  });
}

// ===================== UNDO ============================================
async function loadUndo() {
  const records = await api("/api/undo");
  const el = $("#undo-list");
  el.innerHTML = "";
  if (records.length === 0) el.innerHTML = '<p class="timer">Nothing pending undo.</p>';
  records.forEach((r) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div>${r.label}</div>
      <div class="timer">Undoable for ${r.seconds_remaining}s</div>
      <button class="danger" data-undo>Undo</button>`;
    card.querySelector("[data-undo]").addEventListener("click", async () => {
      await api(`/api/undo/${r.record_id}`, { method: "POST" });
      loadUndo();
    });
    el.appendChild(card);
  });
}

// ===================== LIBRARY =========================================
let selectedAlbumIds = new Set();

async function loadLibrary(q = "") {
  const albums = await api(`/api/library/albums?q=${encodeURIComponent(q)}`);
  const grid = $("#album-grid");
  grid.innerHTML = "";
  albums.forEach((a) => {
    const tile = document.createElement("div");
    tile.className = "album-tile grabbable";
    tile.innerHTML = `
      <img src="/api/library/albums/${a.id}/art" onerror="this.style.visibility='hidden'" />
      <span class="lib-badge">${a.navidrome_library || "unassigned"}</span>
      <input type="checkbox" data-select />
      <div class="meta">${a.albumartist}<br/>${a.album}</div>`;
    tile.querySelector("[data-select]").addEventListener("click", (e) => {
      e.stopPropagation();
      if (e.target.checked) selectedAlbumIds.add(a.id);
      else selectedAlbumIds.delete(a.id);
      updateBulkBar();
    });
    tile.addEventListener("click", (e) => {
      if (e.target.tagName === "INPUT") return;
      openAlbumDetail(a.id);
    });
    attachLongPress(tile, () => [
      { label: "Set navidrome_library…", onClick: () => promptSetLibrary([a.id]) },
      { label: "Reimport / reassign MBID…", onClick: () => openReimport([a.id]) },
    ]);
    grid.appendChild(tile);
  });
}

function updateBulkBar() {
  const bar = $("#bulk-bar");
  bar.hidden = selectedAlbumIds.size === 0;
  $("#bulk-count").textContent = `${selectedAlbumIds.size} selected`;
}

$("#bulk-apply").addEventListener("click", () => promptSetLibrary([...selectedAlbumIds]));

async function promptSetLibrary(albumIds) {
  const value = prompt("navidrome_library value (e.g. kids, worship, holiday, talkradio):");
  if (!value) return;
  await api("/api/library/albums/bulk_fields", {
    method: "POST",
    body: JSON.stringify({ album_ids: albumIds, field: "navidrome_library", value, move: true }),
  });
  selectedAlbumIds.clear();
  updateBulkBar();
  loadLibrary($("#lib-search").value);
}

let searchDebounce;
$("#lib-search").addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => loadLibrary(e.target.value), 300);
});

async function openAlbumDetail(albumId) {
  const detail = await api(`/api/library/albums/${albumId}`);
  const container = document.createElement("div");
  container.innerHTML = `
    <h3>${detail.fields.albumartist} – ${detail.fields.album}</h3>
    <div class="row">
      <label>navidrome_library
        <input type="text" data-field="navidrome_library" value="${detail.fields.navidrome_library || ""}" />
      </label>
      <button data-save-album>Save (auto-move if path changes)</button>
      <button class="secondary" data-reimport>Reimport…</button>
    </div>
    <h4>Tracks</h4>
    <div data-tracks></div>`;

  container.querySelector("[data-save-album]").addEventListener("click", async () => {
    const value = container.querySelector('[data-field="navidrome_library"]').value;
    await api(`/api/library/albums/${albumId}/fields`, {
      method: "POST",
      body: JSON.stringify({ fields: { navidrome_library: value }, move: true }),
    });
    backdrop.remove();
    loadLibrary($("#lib-search").value);
  });
  container.querySelector("[data-reimport]").addEventListener("click", () => {
    backdrop.remove();
    openReimport([albumId]);
  });

  const tracksEl = container.querySelector("[data-tracks]");
  detail.tracks.forEach((t) => {
    const row = document.createElement("div");
    row.className = "card grabbable";
    row.innerHTML = `${t.track}. ${t.title}`;
    attachLongPress(row, () => [
      { label: "Apply tag…", onClick: () => promptApplyTag("item", t.id) },
    ]);
    tracksEl.appendChild(row);
  });

  var backdrop = openModal(container);
}

async function openReimport(albumIds) {
  const container = document.createElement("div");
  container.innerHTML = `
    <h3>Reimport ${albumIds.length} album(s)</h3>
    <div class="row">
      <input type="text" placeholder="MusicBrainz ID or URL (-S)" data-mbid style="flex:1" />
    </div>
    <div class="row">
      <label><input type="checkbox" data-fromscratch /> <b>--from-scratch</b> (erase existing metadata first)</label>
    </div>
    <div class="row">
      <input type="text" placeholder="navidrome_library value to --set (optional)" data-setlib style="flex:1" />
    </div>
    <div class="row">
      <button data-go>Run reimport</button>
    </div>
    <p class="timer">Result goes through the same review/undo flow as a fresh import — check the Inbox tab after running.</p>`;

  const fsBox = container.querySelector("[data-fromscratch]");
  fsBox.addEventListener("change", () => {
    fsBox.parentElement.style.fontWeight = fsBox.checked ? "bold" : "normal";
    fsBox.parentElement.style.color = fsBox.checked ? "var(--danger)" : "inherit";
  });

  container.querySelector("[data-go]").addEventListener("click", async () => {
    const raw = container.querySelector("[data-mbid]").value.trim();
    const searchId = raw ? raw.split("/").pop() : null;
    const fromScratch = fsBox.checked;
    const libValue = container.querySelector("[data-setlib]").value.trim();
    const setFields = libValue ? { navidrome_library: libValue } : {};

    await api("/api/reimport", {
      method: "POST",
      body: JSON.stringify({
        album_ids: albumIds,
        search_id: searchId,
        from_scratch: fromScratch,
        set_fields: setFields,
      }),
    });
    backdrop.remove();
    document.querySelector('#tabs button[data-tab="inbox"]').click();
  });

  var backdrop = openModal(container);
}

// ===================== TAGS ============================================
async function loadTags() {
  const data = await api("/api/tags");
  const el = $("#tag-fields");
  el.innerHTML = "";
  Object.entries(data).forEach(([field, values]) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h3>${field}</h3>
      <div class="tags-values"></div>
      <div class="row">
        <input type="text" placeholder="new value" data-new />
        <button data-add>Add</button>
      </div>`;
    const valuesEl = card.querySelector(".tags-values");
    values.forEach((v) => {
      const chip = document.createElement("span");
      chip.className = "tag-chip grabbable";
      chip.textContent = v;
      attachLongPress(chip, () => [
        {
          label: "Apply to album/track…",
          onClick: () => {
            const id = prompt("Album or track ID to apply this tag to:");
            const scope = confirm("OK = album (writes to all tracks), Cancel = single track") ? "album" : "item";
            if (id) applyTag(field, v, scope, parseInt(id, 10));
          },
        },
      ]);
      valuesEl.appendChild(chip);
    });
    card.querySelector("[data-add]").addEventListener("click", async () => {
      const val = card.querySelector("[data-new]").value.trim();
      if (!val) return;
      await api(`/api/tags/${field}`, { method: "POST", body: JSON.stringify({ value: val }) });
      loadTags();
    });
    el.appendChild(card);
  });
}

async function applyTag(field, value, scope, id) {
  await api(`/api/tags/${field}/apply`, {
    method: "POST",
    body: JSON.stringify({ value, scope, id, add: true }),
  });
  alert("Applied.");
}

function promptApplyTag(scope, id) {
  const field = prompt("Tag field (e.g. mood):", "mood");
  if (!field) return;
  const value = prompt("Tag value:");
  if (!value) return;
  applyTag(field, value, scope, id);
}

// -- init ---------------------------------------------------------------
loadInbox();
setInterval(() => {
  if ($("#tab-inbox").classList.contains("active")) loadInbox();
  if ($("#tab-undo").classList.contains("active")) loadUndo();
}, 5000);

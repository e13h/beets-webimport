// beets-webimport frontend. Plain fetch + DOM.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// Safe for both element content and quoted attribute values.
const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function escapeHtml(str) {
  if (str === null || str === undefined || str === "") return "";
  return String(str).replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
}

// -- Toast notifications ------------------------------------------------
function showToast(message, type = "info", duration = 4000) {
  const container = $("#toast-container") || document.body;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  let icon = "";
  if (type === "in-progress") icon = '<span class="spinner"></span>';
  else if (type === "success") icon = '<span style="color:var(--ok)">✓</span>';
  else if (type === "error") icon = '<span style="color:var(--danger)">⚠</span>';

  toast.innerHTML = `
    ${icon}
    <div class="toast-msg">${escapeHtml(message)}</div>
    <button class="toast-close" aria-label="Dismiss">&times;</button>`;

  const dismiss = () => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px) scale(0.96)";
    setTimeout(() => toast.remove(), 300);
  };

  toast.querySelector(".toast-close").addEventListener("click", dismiss);
  if (duration > 0) setTimeout(dismiss, duration);

  container.appendChild(toast);
  return { toast, dismiss };
}

function createProgressToast(initialMessage) {
  const container = $("#toast-container") || document.body;
  const toast = document.createElement("div");
  toast.className = "toast in-progress";
  toast.innerHTML = `
    <span class="spinner"></span>
    <div class="toast-msg">${escapeHtml(initialMessage)}</div>
    <button class="toast-close" aria-label="Dismiss">&times;</button>`;

  let autoDismissTimer = null;
  const dismiss = () => {
    if (autoDismissTimer) clearTimeout(autoDismissTimer);
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px) scale(0.96)";
    setTimeout(() => toast.remove(), 300);
  };

  toast.querySelector(".toast-close").addEventListener("click", dismiss);
  container.appendChild(toast);

  return {
    update(message, type = "in-progress") {
      toast.className = `toast ${type}`;
      let icon = "";
      if (type === "in-progress") icon = '<span class="spinner"></span>';
      else if (type === "success") icon = '<span style="color:var(--ok)">✓</span>';
      else if (type === "error") icon = '<span style="color:var(--danger)">⚠</span>';
      toast.innerHTML = `
        ${icon}
        <div class="toast-msg">${escapeHtml(message)}</div>
        <button class="toast-close" aria-label="Dismiss">&times;</button>`;
      toast.querySelector(".toast-close").addEventListener("click", dismiss);
    },
    done(message, duration = 4000) {
      this.update(message, "success");
      autoDismissTimer = setTimeout(dismiss, duration);
    },
    error(message, duration = 6000) {
      this.update(message, "error");
      autoDismissTimer = setTimeout(dismiss, duration);
    },
    dismiss,
  };
}

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    // not JSON
  }
  if (!res.ok) {
    if (res.status === 409 && data && data.conflict) {
      const err = new Error(data.message || "Placement conflict");
      err.conflictData = data;
      err.status = 409;
      throw err;
    }
    let errDetail = `${path}: ${res.status}`;
    if (data && data.error) errDetail = data.error;
    throw new Error(errDetail);
  }
  return data;
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
  if (tab === "library") {
    loadListeningGroups();
    loadLibrary();
  }
  if (tab === "tags") loadTags();
}

// -- modal helper with visible Close button and Escape key listener ------
function openModal(contentEl) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const modal = document.createElement("div");
  modal.className = "modal";

  const closeBtn = document.createElement("button");
  closeBtn.className = "modal-close-btn";
  closeBtn.innerHTML = "&times;";
  closeBtn.setAttribute("aria-label", "Close modal");
  modal.appendChild(closeBtn);

  modal.appendChild(contentEl);
  backdrop.appendChild(modal);

  function close() {
    document.removeEventListener("keydown", onKeyDown);
    backdrop.remove();
  }

  function onKeyDown(e) {
    if (e.key === "Escape") {
      close();
    }
  }

  document.addEventListener("keydown", onKeyDown);
  closeBtn.addEventListener("click", close);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) close();
  });

  backdrop.close = close;
  $("#modal-root").appendChild(backdrop);
  return backdrop;
}

// long-press -> menu, touch-friendly equivalent of drag-and-drop
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
// After starting a Direct ID import, the targeted lookup is fast and
// usually yields exactly one candidate (or an empty-candidate error
// state) -- open the review modal as soon as it registers instead of
// making the user hunt for the card.
async function openReviewWhenReady(path, maxWaitMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    await new Promise((r) => setTimeout(r, 500));
    let data;
    try {
      data = await api("/api/inbox");
    } catch {
      continue; // transient poll failure -- keep waiting
    }
    const pr = data.pending_review.find((p) => p.path === path);
    if (pr) {
      openReview(pr);
      return;
    }
    // Task finished without registering a review (e.g. skip/abort):
    // stop polling once the folder is no longer in progress.
    const dir = (data.inbox_dirs || []).find((d) => d.path === path);
    if (dir && !dir.in_progress) return;
  }
}

// Open Direct-ID forms and their in-progress text, keyed by folder
// path -- preserved across the 5s loadInbox() re-render so a mid-typing
// form isn't wiped by the polling refresh. focusedIdInputPath tracks
// which form's input has focus so it can be restored after re-render.
const openIdForms = new Map();
let focusedIdInputPath = null;
// A real click/tap outside the Direct-ID form clears the focus tracker
// (blur is unusable for this: it also fires during the poll re-render's
// DOM teardown). Keyboard Tab-away is not covered — acceptable, since
// re-focusing then is harmless.
document.addEventListener("pointerdown", (e) => {
  if (!focusedIdInputPath) return;
  if (e.target.closest?.("[data-id-form]")) return;
  focusedIdInputPath = null;
}, true);

async function loadInbox() {
  let data;
  try {
    data = await api("/api/inbox");
  } catch (err) {
    showToast(`Failed to load inbox: ${err.message}`, "error");
    return;
  }

  const dirsEl = $("#inbox-dirs");
  const livePaths = new Set();
  dirsEl.innerHTML = "";
  if (data.inbox_dirs.length === 0) {
    dirsEl.innerHTML = '<p class="timer">Inbox is empty.</p>';
  }

  data.inbox_dirs.forEach((dirInfo) => {
    const isObj = typeof dirInfo === "object" && dirInfo !== null;
    const path = isObj ? dirInfo.path : dirInfo;
    livePaths.add(path);
    const imported = isObj ? !!dirInfo.imported : false;
    const albumId = isObj ? dirInfo.album_id : null;
    const inProgress = isObj ? !!dirInfo.in_progress : false;
    const pendingReview = isObj ? !!dirInfo.pending_review : false;

    const card = document.createElement("div");
    card.className = "card" + (imported ? " imported" : "");

    let badgeHtml = "";
    if (imported) {
      badgeHtml = '<span class="badge imported">Imported</span> ';
    } else if (inProgress) {
      badgeHtml = '<span class="badge pending">In Progress</span> ';
    } else if (pendingReview) {
      badgeHtml = '<span class="badge pending">Pending Review</span> ';
    }

    let actionsHtml = "";
    if (imported) {
      actionsHtml = `
        <button class="secondary" data-reimport>Re-import</button>
        <button class="secondary" data-id-toggle>Import with ID…</button>
        <button class="danger" data-delete>Delete from inbox</button>`;
    } else if (inProgress || pendingReview) {
      actionsHtml = `
        <button disabled class="secondary">${inProgress ? "Searching Candidates…" : "Awaiting Review"}</button>`;
    } else {
      actionsHtml = `
        <button data-start>Start import</button>
        <button class="secondary" data-id-toggle>Import with ID…</button>`;
    }

    const idFormHtml = `
      <div class="row" data-id-form style="display:none">
        <input type="text" placeholder="Paste MusicBrainz ID or URL" style="flex:1" data-id-input />
        <button data-id-go>Start import with ID</button>
      </div>`;

    card.innerHTML = `
      <div class="path">${badgeHtml}${escapeHtml(path)}</div>
      <div class="row">
        ${actionsHtml}
      </div>
      ${idFormHtml}`;

    const idToggle = card.querySelector("[data-id-toggle]");
    const idForm = card.querySelector("[data-id-form]");
    const idInput = card.querySelector("[data-id-input]");
    // Restore open-state and typed text across the 5s polling re-render
    // (focus is restored after appendChild -- focus() is a silent no-op
    // on elements not yet in the document). openIdForms.has(), not
    // truthiness -- an open-but-empty form stores "".
    const isOpen = openIdForms.has(path);
    if (isOpen) {
      idForm.style.display = "flex";
      idInput.value = openIdForms.get(path) || "";
    }
    if (idToggle) {
      idToggle.addEventListener("click", () => {
        const visible = idForm.style.display !== "none";
        idForm.style.display = visible ? "none" : "flex";
        if (visible) {
          openIdForms.delete(path);
          if (focusedIdInputPath === path) focusedIdInputPath = null;
        } else {
          openIdForms.set(path, idInput.value);
          idInput.focus();
        }
      });
    }
    idInput.addEventListener("input", () => openIdForms.set(path, idInput.value));
    // Track focus for restore after the poll re-render. Do NOT clear on
    // blur: Chrome fires blur with isConnected===true while tearing down
    // the old DOM, so blur can't distinguish teardown from a real
    // click-away. Instead, a document-level pointerdown outside the form
    // (below) clears the tracker.
    idInput.addEventListener("focus", () => (focusedIdInputPath = path));

    const idGo = card.querySelector("[data-id-go]");
    if (idGo) {
      const resetIdGo = () => {
        idGo.disabled = false;
        idGo.textContent = "Start import with ID";
      };
      idGo.addEventListener("click", async () => {
        // Raw pass-through: no client-side URL parsing or extraction.
        const raw = idInput.value.trim();
        if (!raw) return;
        idGo.disabled = true;
        idGo.textContent = "Starting…";
        try {
          if (imported) {
            if (!albumId) {
              showToast(
                "Cannot Direct-ID-import: library album ID unavailable from marker data. Use Re-import instead.",
                "error"
              );
              resetIdGo();
              return;
            }
            await api("/api/reimport", {
              method: "POST",
              body: JSON.stringify({
                album_ids: [albumId],
                search_id: raw,
                from_scratch: false,
                set_fields: {},
              }),
            });
          } else {
            await api("/api/inbox/start", {
              method: "POST",
              body: JSON.stringify({
                paths: [path],
                search_ids: { [path]: raw },
              }),
            });
          }
          showToast(`Started Direct ID import for ${path}`, "info", 3000);
          loadInbox();
          if (!imported) openReviewWhenReady(path);
        } catch (err) {
          showToast(`Failed to start import: ${err.message}`, "error");
          resetIdGo();
        }
      });
    }

    if (imported) {
      card.querySelector("[data-reimport]").addEventListener("click", () => {
        if (albumId) openReimport([albumId]);
        else showToast("Album ID not available for reimport.", "error");
      });
      card.querySelector("[data-delete]").addEventListener("click", async () => {
        if (!confirm(`Delete "${path}" from inbox?`)) return;
        try {
          await api("/api/inbox/delete", {
            method: "POST",
            body: JSON.stringify({ path }),
          });
          showToast(`Deleted "${path}" from inbox.`, "success");
          loadInbox();
        } catch (err) {
          showToast(`Failed to delete: ${err.message}`, "error");
        }
      });
    } else if (!inProgress && !pendingReview) {
      const startBtn = card.querySelector("[data-start]");
      startBtn.addEventListener("click", async () => {
        startBtn.disabled = true;
        startBtn.textContent = "Starting…";
        try {
          await api("/api/inbox/start", {
            method: "POST",
            body: JSON.stringify({ paths: [path] }),
          });
          showToast(`Started candidate search for ${path}`, "info", 3000);
          loadInbox();
        } catch (err) {
          showToast(`Failed to start import: ${err.message}`, "error");
          startBtn.disabled = false;
          startBtn.textContent = "Start import";
        }
      });
    }

    dirsEl.appendChild(card);

    // Focus restore must happen after appendChild: element.focus() does
    // nothing while the element is detached (card is appended here).
    if (isOpen && focusedIdInputPath === path) {
      idInput.focus();
    }
  });

  for (const p of [...openIdForms.keys()]) {
    if (!livePaths.has(p)) {
      openIdForms.delete(p);
      if (focusedIdInputPath === p) focusedIdInputPath = null;
    }
  }

  const pendingEl = $("#pending-reviews");
  pendingEl.innerHTML = "";
  if (data.pending_review.length === 0) {
    pendingEl.innerHTML = '<p class="timer">No items pending review.</p>';
  }
  data.pending_review.forEach((pr) => {
    const card = document.createElement("div");
    card.className = "card";
    const statusText = pr.kind === "duplicate" ? "Possible duplicate" : "Candidates ready for review";

    card.innerHTML = `
      <div class="path">${escapeHtml(pr.path)}</div>
      <div style="margin: 6px 0; font-size: 13px;">${statusText}</div>
      <button data-review>Review</button>`;
    card.querySelector("[data-review]").addEventListener("click", () => openReview(pr));
    pendingEl.appendChild(card);
  });
}

async function openReview(pr) {
  if (pr.kind === "duplicate") return openDuplicateReview(pr);

  const container = document.createElement("div");
  container.innerHTML = `<h3>${escapeHtml(pr.path)}</h3>`;
  const itunesCard = document.createElement("div");
  container.appendChild(itunesCard);
  const list = document.createElement("div");
  container.appendChild(list);
  // Set once the iTunes art card loads; read when a decision is sent.
  let useItunesArt = () => false;
  loadItunesArtCard(itunesCard, pr.path, container).then((getter) => { useItunesArt = getter; });

  let focusedIndex = null;

  function renderCandidates() {
    list.innerHTML = "";
    pr.payload.candidates.forEach((c, i) => {
      const div = document.createElement("div");
      div.className = "candidate" + (focusedIndex === i ? " focused" : "");
      const artistAlbum = c.album ? `${c.artist} – ${c.album}` : `${c.artist} – ${c.title}`;
      div.innerHTML = `
        <div>${escapeHtml(artistAlbum)} ${c.year ? `(${c.year})` : ""}</div>
        <div class="dist">distance ${c.distance} · ${escapeHtml(c.data_source || "?")}</div>
        <div class="art-compare" data-art></div>
        <div class="row">
          <button data-select>Select</button>
        </div>`;
      div.addEventListener("click", () => {
        if (focusedIndex !== i) {
          focusedIndex = i;
          renderCandidates();
          loadArtCompare($(".candidate.focused", list), pr, c);
        }
      });
      div.querySelector("[data-select]").addEventListener("click", async (e) => {
        e.stopPropagation();
        const toast = createProgressToast(`Applying import for ${pr.path}…`);
        try {
          await decide(pr.task_id, { action: "select", index: i, use_itunes_art: useItunesArt() });
          backdrop.close();
          loadInbox();
          toast.done(`Import applied successfully for ${pr.path}!`);
        } catch (err) {
          toast.error(`Apply failed: ${err.message}`);
        }
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

  // Matched automatically through the album's Apple Music link.
  const via = pr.payload.matched_via;
  if (via && via.source === "apple_music") {
    const n = via.release_ids.length;
    const banner = document.createElement("div");
    banner.className = "matched-via";
    banner.innerHTML = via.fallback
      ? `<div>Found ${n === 1 ? "a MusicBrainz release" : `${n} MusicBrainz releases`} linked to this album's Apple Music listing,
           but couldn't load ${n === 1 ? "it" : "them"}, so these are normal search results.</div>`
      : `<div>✓ Matched via Apple Music link: ${n === 1 ? "the MusicBrainz release" : `${n} MusicBrainz releases`}
           linked to iTunes album <a href="https://music.apple.com/album/${via.collection_id}" target="_blank" rel="noopener">${via.collection_id}</a>.</div>
         <div class="row"><button class="secondary" data-search-normally>Search normally instead</button></div>`;
    banner.querySelector("[data-search-normally]")?.addEventListener("click", async () => {
      const toast = createProgressToast("Running normal candidate search…");
      try {
        await decide(pr.task_id, { action: "search_id", search_id: "" });
        backdrop.close();
        loadInbox();
        toast.done("Candidate search started.");
      } catch (err) {
        toast.error(`Search failed: ${err.message}`);
      }
    });
    container.insertBefore(banner, list);
  }

  // Direct ID Import failure state: a pre-specified ID yielded zero
  // candidates (bad ID, 404, network failure). Surface it for
  // correction instead of showing an empty candidate list.
  if (!pr.payload.candidates.length && pr.payload.attempted_search_id) {
    const errBanner = document.createElement("div");
    errBanner.className = "id-error-banner";
    errBanner.innerHTML = `
      <div>⚠ No candidate found for ID <b>${escapeHtml(pr.payload.attempted_search_id)}</b>.</div>
      <div class="row">
        <input type="text" placeholder="Paste a different MusicBrainz ID or URL" style="flex:1" data-retry-id />
        <button data-retry-go>Try ID</button>
        <button class="secondary" data-auto-search>Auto-search instead</button>
      </div>`;
    container.appendChild(errBanner);

    errBanner.querySelector("[data-retry-go]").addEventListener("click", async () => {
      const raw = errBanner.querySelector("[data-retry-id]").value.trim();
      if (!raw) return;
      const toast = createProgressToast(`Searching candidate with ID ${raw}…`);
      try {
        await decide(pr.task_id, { action: "search_id", search_id: raw });
        backdrop.close();
        loadInbox();
        toast.done("Candidate lookup updated.");
      } catch (err) {
        toast.error(`Search failed: ${err.message}`);
      }
    });

    errBanner.querySelector("[data-auto-search]").addEventListener("click", async () => {
      const toast = createProgressToast("Running normal candidate search…");
      try {
        await decide(pr.task_id, { action: "search_id", search_id: "" });
        backdrop.close();
        loadInbox();
        toast.done("Candidate search started.");
      } catch (err) {
        toast.error(`Search failed: ${err.message}`);
      }
    });
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
    const toast = createProgressToast(`Searching candidate with ID ${id}…`);
    try {
      await decide(pr.task_id, { action: "search_id", search_id: id });
      backdrop.close();
      loadInbox();
      toast.done(`Candidate lookup updated.`);
    } catch (err) {
      toast.error(`Search failed: ${err.message}`);
    }
  });

  idRow.querySelector("[data-asis]").addEventListener("click", async () => {
    const toast = createProgressToast(`Applying import as-is for ${pr.path}…`);
    try {
      await decide(pr.task_id, { action: "asis", use_itunes_art: useItunesArt() });
      backdrop.close();
      loadInbox();
      toast.done(`Imported as-is.`);
    } catch (err) {
      toast.error(`Apply failed: ${err.message}`);
    }
  });

  idRow.querySelector("[data-skip]").addEventListener("click", async () => {
    try {
      await decide(pr.task_id, { action: "skip" });
      backdrop.close();
      loadInbox();
      showToast(`Skipped ${pr.path}`, "info");
    } catch (err) {
      showToast(`Skip failed: ${err.message}`, "error");
    }
  });

  container.appendChild(idRow);
  var backdrop = openModal(container);
}

// iTunes purchases: offer the store's artwork instead of Cover Art Archive.
// Resolves to a function returning whether to use it (false if no card).
async function loadItunesArtCard(host, path, reviewContainer) {
  let info;
  try {
    info = await api(`/api/inbox/itunes_art?path=${encodeURIComponent(path)}`);
  } catch {
    return () => false;
  }
  if (!info.detected) return () => false;

  if (info.error) {
    host.innerHTML = `<div class="itunes-card"><div>
        <div class="itunes-title">iTunes purchase detected</div>
        <div class="warn-text">${escapeHtml(info.error)}</div>
      </div></div>`;
    return () => false;
  }

  const size = info.width && info.height ? `${info.width} × ${info.height} px · ` : "";
  const format = (info.mime || "").replace("image/", "").toUpperCase();
  host.innerHTML = `
    <div class="itunes-card">
      <a class="art-frame" href="${info.image_url}" target="_blank" rel="noopener" title="Open full size">
        <img src="${info.image_url}" alt="iTunes artwork" />
      </a>
      <div class="itunes-body">
        <div class="itunes-title">iTunes purchase detected</div>
        <div class="muted">${escapeHtml(info.collection_name || "")}${info.artist ? " — " + escapeHtml(info.artist) : ""}
          ${info.store_url ? ` · <a href="${escapeHtml(info.store_url)}" target="_blank" rel="noopener">Apple Music</a>` : ""}</div>
        <div class="muted">${size}${explorerBytes(info.bytes)} · ${escapeHtml(format)}</div>
        <label class="itunes-toggle"><input type="checkbox" data-use-itunes ${info.existing_cover ? "" : "checked"} />
          Use iTunes art for this import</label>
        <div class="muted itunes-note">${info.existing_cover
          ? `This folder already has <b>${escapeHtml(info.existing_cover)}</b>, which will be used unless you check this (it's kept, renamed to ${escapeHtml(info.existing_cover)}.before-itunes).`
          : "Saved as cover.jpg in the inbox folder, so beets embeds it instead of the Cover Art Archive image."}</div>
      </div>
    </div>`;
  const box = host.querySelector("[data-use-itunes]");
  const sync = () => reviewContainer.classList.toggle("use-itunes-art", box.checked);
  box.addEventListener("change", sync);
  sync();
  return () => box.checked;
}

async function loadArtCompare(candidateEl, pr, candidate) {
  if (!candidateEl) return;
  const holder = candidateEl.querySelector("[data-art]");
  if (!holder) return;

  const maxRetries = 2;
  let attempt = 0;

  async function tryFetch() {
    if (attempt === 0) {
      holder.innerHTML = '<span class="spinner"></span> <span class="timer">Resolving art…</span>';
    } else {
      holder.innerHTML = `<span class="spinner"></span> <span class="timer">Retrying art lookup (${attempt}/${maxRetries})…</span>`;
    }

    try {
      const result = await api("/api/coverart/resolve", {
        method: "POST",
        body: JSON.stringify({
          item_dir: pr.path,
          release_mbid: candidate.album_id,
          release_group_mbid: null,
        }),
      });

      if (result.unavailable && !result.source_url && !result.resolved_url) {
        if (attempt < maxRetries) {
          attempt++;
          const delay = attempt === 1 ? 1500 : 3000;
          setTimeout(tryFetch, delay);
          return;
        }
        renderRetryFallback();
        return;
      }

      holder.innerHTML = `
        ${result.source_url ? `<img src="${result.source_url}" alt="source" />` : "<span>no source art</span>"}
        ${result.resolved_url ? `<img src="${result.resolved_url}" alt="resolved" />` : "<span>no resolved art</span>"}
        <span class="art-badge ${result.match ? "match" : "mismatch"}">${result.match ? "match" : "differs"}</span>`;
    } catch (err) {
      if (attempt < maxRetries) {
        attempt++;
        const delay = attempt === 1 ? 1500 : 3000;
        setTimeout(tryFetch, delay);
        return;
      }
      renderRetryFallback();
    }
  }

  function renderRetryFallback() {
    holder.innerHTML = `
      <div class="art-unavailable">
        <span class="timer">art service unavailable</span>
        <button class="art-preview-retry secondary">Retry lookup</button>
      </div>`;
    holder.querySelector(".art-preview-retry")?.addEventListener("click", (e) => {
      e.stopPropagation();
      attempt = 0;
      tryFetch();
    });
  }

  tryFetch();
}

async function openDuplicateReview(pr) {
  const container = document.createElement("div");
  container.innerHTML = `
    <h3>Possible duplicate — ${escapeHtml(pr.path)}</h3>
    <ul>${pr.payload.duplicates.map((d) => `<li>${escapeHtml(d.album)}</li>`).join("")}</ul>
    <div class="row">
      <button data-keep-both>Keep both</button>
      <button class="secondary" data-remove-old>Replace existing</button>
      <button class="danger" data-skip>Skip new</button>
    </div>`;

  container.querySelector("[data-keep-both]").addEventListener("click", async () => {
    const toast = createProgressToast("Applying decision: keep both…");
    try {
      await decide(pr.task_id, { action: "keep_both" });
      backdrop.close();
      loadInbox();
      toast.done("Saved (keeping both).");
    } catch (err) {
      toast.error(`Decision failed: ${err.message}`);
    }
  });

  container.querySelector("[data-remove-old]").addEventListener("click", async () => {
    const toast = createProgressToast("Applying decision: replacing existing…");
    try {
      await decide(pr.task_id, { action: "remove_old" });
      backdrop.close();
      loadInbox();
      toast.done("Replaced existing album.");
    } catch (err) {
      toast.error(`Decision failed: ${err.message}`);
    }
  });

  container.querySelector("[data-skip]").addEventListener("click", async () => {
    try {
      await decide(pr.task_id, { action: "skip" });
      backdrop.close();
      loadInbox();
      showToast("Skipped duplicate import.", "info");
    } catch (err) {
      showToast(`Decision failed: ${err.message}`, "error");
    }
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
  let records;
  try {
    records = await api("/api/undo");
  } catch (err) {
    showToast(`Failed to load undo items: ${err.message}`, "error");
    return;
  }

  const el = $("#undo-list");
  el.innerHTML = "";
  if (records.length === 0) el.innerHTML = '<p class="timer">Nothing pending undo.</p>';
  records.forEach((r) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div>${escapeHtml(r.label)}</div>
      <div class="timer">Undoable for ${r.seconds_remaining}s</div>
      <button class="danger" data-undo>Undo</button>`;
    card.querySelector("[data-undo]").addEventListener("click", async () => {
      try {
        await api(`/api/undo/${r.record_id}`, { method: "POST" });
        showToast(`Undid import: ${r.label}`, "success");
        loadUndo();
      } catch (err) {
        showToast(`Undo failed: ${err.message}`, "error");
      }
    });
    el.appendChild(card);
  });
}

// ===================== LISTENING GROUPS & CONFLICTS =================
async function loadListeningGroups() {
  try {
    const groups = await api("/api/library/listening_groups");
    const datalist = $("#listening-groups-list");
    if (datalist && Array.isArray(groups)) {
      datalist.innerHTML = groups.map((g) => `<option value="${escapeHtml(g)}"></option>`).join("");
    }
  } catch {
    // best-effort
  }
}

function openPlacementConflictModal(conflictData, onResolve) {
  const container = document.createElement("div");
  container.innerHTML = `
    <h3>Placement Conflict</h3>
    <p>A file move conflict occurred at destination path:</p>
    <pre class="path" style="white-space:pre-wrap; word-break:break-all;">${escapeHtml(conflictData.destination)}</pre>
    <p style="font-size:13px; color:var(--muted);">Choose how to resolve this collision:</p>
    <div class="row">
      <button data-keep-both>Keep both</button>
      <button class="secondary" data-overwrite>Overwrite existing</button>
      <button class="danger" data-skip>Skip edit (revert)</button>
    </div>`;

  const backdrop = openModal(container);

  container.querySelector("[data-keep-both]").addEventListener("click", () => {
    backdrop.close();
    onResolve("keep_both");
  });
  container.querySelector("[data-overwrite]").addEventListener("click", () => {
    backdrop.close();
    onResolve("overwrite");
  });
  container.querySelector("[data-skip]").addEventListener("click", () => {
    backdrop.close();
    onResolve("skip");
  });
}

// ===================== LIBRARY =========================================
let selectedAlbumIds = new Set();

async function loadLibrary(q = "") {
  let albums;
  try {
    albums = await api(`/api/library/albums?q=${encodeURIComponent(q)}`);
  } catch (err) {
    showToast(`Failed to search library: ${err.message}`, "error");
    return;
  }

  const grid = $("#album-grid");
  grid.innerHTML = "";

  if (albums.length === 0) {
    const emptyEl = document.createElement("div");
    emptyEl.className = "empty-state muted";
    const trimmed = q.trim();
    if (trimmed) {
      emptyEl.innerHTML = `No albums matching &ldquo;${escapeHtml(trimmed)}&rdquo; found.`;
    } else {
      emptyEl.textContent = "No albums in library.";
    }
    grid.appendChild(emptyEl);
    return;
  }

  albums.forEach((a) => {
    const tile = document.createElement("div");
    tile.className = "album-tile grabbable";
    tile.innerHTML = `
      <div class="art-wrap">
        <img src="/api/library/albums/${a.id}/art?thumb=1" loading="lazy" decoding="async" alt=""
             onload="this.classList.add('loaded')" onerror="this.parentElement.classList.add('no-art')" />
        <div class="art-placeholder"><span>No Art</span></div>
      </div>
      <span class="lib-badge">${escapeHtml(a.navidrome_library || "unassigned")}</span>
      <input type="checkbox" data-select />
      <div class="meta">${escapeHtml(a.albumartist)}<br/>${escapeHtml(a.album)}</div>`;

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

$("#bulk-apply")?.addEventListener("click", () => promptSetLibrary([...selectedAlbumIds]));

async function promptSetLibrary(albumIds) {
  const container = document.createElement("div");
  container.innerHTML = `
    <h3>Set Listening Group (navidrome_library)</h3>
    <p style="font-size:13px; color:var(--muted);">Select an existing listening group or type a new one:</p>
    <div class="row">
      <input type="text" list="listening-groups-list" placeholder="e.g. kids, worship, holiday, talkradio" style="flex:1" data-val />
      <button data-apply>Apply</button>
      <button class="secondary" data-cancel>Cancel</button>
    </div>`;

  const input = container.querySelector("[data-val]");
  const applyBtn = container.querySelector("[data-apply]");
  const cancelBtn = container.querySelector("[data-cancel]");

  const backdrop = openModal(container);
  input.focus();

  cancelBtn.addEventListener("click", () => backdrop.close());

  const doApply = async (conflictResolution = null) => {
    const value = input.value.trim();
    if (!value) return;
    try {
      await api("/api/library/albums/bulk_fields", {
        method: "POST",
        body: JSON.stringify({
          album_ids: albumIds,
          field: "navidrome_library",
          value,
          move: true,
          conflict_resolution: conflictResolution,
        }),
      });
      backdrop.close();
      if (conflictResolution === "skip") {
        showToast("Skipped field update (reverted).", "info");
      } else {
        showToast(`Updated navidrome_library on ${albumIds.length} album(s).`, "success");
      }
      selectedAlbumIds.clear();
      updateBulkBar();
      loadListeningGroups();
      loadLibrary($("#lib-search").value);
    } catch (err) {
      if (err.conflictData) {
        openPlacementConflictModal(err.conflictData, (res) => doApply(res));
      } else {
        showToast(`Failed to update field: ${err.message}`, "error");
      }
    }
  };

  applyBtn.addEventListener("click", () => doApply());
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doApply();
  });
}

let searchDebounce;
$("#lib-search")?.addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => loadLibrary(e.target.value), 300);
});

async function openAlbumDetail(albumId) {
  let detail;
  try {
    detail = await api(`/api/library/albums/${albumId}`);
  } catch (err) {
    showToast(`Failed to load album details: ${err.message}`, "error");
    return;
  }

  const container = document.createElement("div");
  container.innerHTML = `
    <h3>${escapeHtml(detail.fields.albumartist)} – ${escapeHtml(detail.fields.album)}</h3>
    <div class="row">
      <label>navidrome_library
        <input type="text" list="listening-groups-list" data-field="navidrome_library" value="${escapeHtml(detail.fields.navidrome_library || "")}" />
      </label>
      <button data-save-album>Save (auto-move if path changes)</button>
      <button class="secondary" data-reimport>Reimport…</button>
    </div>
    <div data-explorer></div>`;

  const saveAlbumWithConflict = async (conflictResolution = null) => {
    const value = container.querySelector('[data-field="navidrome_library"]').value;
    try {
      await api(`/api/library/albums/${albumId}/fields`, {
        method: "POST",
        body: JSON.stringify({
          fields: { navidrome_library: value },
          move: true,
          conflict_resolution: conflictResolution,
        }),
      });
      if (conflictResolution === "skip") {
        showToast("Edit skipped (reverted).", "info");
      } else {
        showToast("Album saved.", "success");
      }
      backdrop.close();
      loadListeningGroups();
      loadLibrary($("#lib-search").value);
    } catch (err) {
      if (err.conflictData) {
        openPlacementConflictModal(err.conflictData, (res) => saveAlbumWithConflict(res));
      } else {
        showToast(`Save failed: ${err.message}`, "error");
      }
    }
  };

  container.querySelector("[data-save-album]").addEventListener("click", () => saveAlbumWithConflict());

  container.querySelector("[data-reimport]").addEventListener("click", () => {
    backdrop.close();
    openReimport([albumId]);
  });

  renderAlbumExplorer(container.querySelector("[data-explorer]"), albumId);

  var backdrop = openModal(container);
  container.parentElement.classList.add("modal-wide");
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
      <input type="text" placeholder="navidrome_library value to --set (optional)" data-setlib list="listening-groups-list" style="flex:1" />
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

    const toast = createProgressToast(`Starting reimport for ${albumIds.length} album(s)…`);
    try {
      await api("/api/reimport", {
        method: "POST",
        body: JSON.stringify({
          album_ids: albumIds,
          search_id: searchId,
          from_scratch: fromScratch,
          set_fields: setFields,
        }),
      });
      backdrop.close();
      toast.done("Reimport queued. Check Inbox tab.");
      document.querySelector('#tabs button[data-tab="inbox"]').click();
    } catch (err) {
      toast.error(`Reimport failed: ${err.message}`);
    }
  });

  var backdrop = openModal(container);
}

// ===================== TAGS ============================================
async function loadTags() {
  let data;
  try {
    data = await api("/api/tags");
  } catch (err) {
    showToast(`Failed to load tags: ${err.message}`, "error");
    return;
  }

  const el = $("#tag-fields");
  el.innerHTML = "";
  Object.entries(data).forEach(([field, values]) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <h3>${escapeHtml(field)}</h3>
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
      try {
        await api(`/api/tags/${field}`, { method: "POST", body: JSON.stringify({ value: val }) });
        loadTags();
      } catch (err) {
        showToast(`Failed to add tag value: ${err.message}`, "error");
      }
    });
    el.appendChild(card);
  });
}

async function applyTag(field, value, scope, id) {
  try {
    await api(`/api/tags/${field}/apply`, {
      method: "POST",
      body: JSON.stringify({ value, scope, id, add: true }),
    });
    showToast(`Applied ${field}="${value}" to ${scope} #${id}`, "success");
  } catch (err) {
    showToast(`Failed to apply tag: ${err.message}`, "error");
  }
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
  if ($("#tab-inbox")?.classList.contains("active")) loadInbox();
  if ($("#tab-undo")?.classList.contains("active")) loadUndo();
}, 5000);

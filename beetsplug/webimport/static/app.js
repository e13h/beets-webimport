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
    const err = new Error(errDetail);
    err.data = data;
    err.status = res.status;
    throw err;
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
    [data, backfillState] = await Promise.all([api("/api/inbox"), api("/api/backfill").catch(() => null)]);
  } catch (err) {
    showToast(`Failed to load inbox: ${err.message}`, "error");
    return;
  }
  renderBackfillBar();

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
        <button class="danger" data-release title="Imported before move mode: the inbox still holds a copy. Removes it once every file is checked to be restorable from the library (Undo import).">Remove inbox copy</button>`;
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
      ${backfillLineHtml(path)}
      <div class="row">
        ${actionsHtml}
      </div>
      ${idFormHtml}`;
    card.querySelector("[data-backfill]")?.addEventListener("click", () => openBackfillModal([path]));

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
      card.querySelector("[data-release]").addEventListener("click", async (e) => {
        e.target.disabled = true;
        const toast = createProgressToast(`Checking ${path}…`);
        try {
          const r = await api("/api/inbox/release", { method: "POST", body: JSON.stringify({ path }) });
          toast.done(`Removed the inbox copy: ${r.audio_files} track${r.audio_files === 1 ? "" : "s"} restorable with Undo import${r.other_files ? `, ${r.other_files} other file${r.other_files === 1 ? "" : "s"} kept with the album` : ""}.`);
          loadInbox();
        } catch (err) {
          e.target.disabled = false;
          const problems = err.data?.problems?.length ? ` ${err.data.problems.join(" ")}` : "";
          toast.error(`Kept the inbox copy: ${err.message}${problems}`);
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

// "Tags after import": the files' tags now vs. after importing with the
// focused candidate (renderTagPreview in explorer.js). One request per
// candidate, cached for the life of the modal.
function createTagPreviewSection(host, pr) {
  host.className = "tag-preview-section";
  host.innerHTML = `<div class="tp-head"><h4>Tags after import</h4><span class="tp-chips"></span></div><div class="tp-body"></div>`;
  const chipsEl = host.querySelector(".tp-chips");
  const bodyEl = host.querySelector(".tp-body");
  const cache = new Map();
  let current = null;
  async function focusCandidate(c) {
    current = c;
    if (!c) {
      chipsEl.innerHTML = "";
      bodyEl.innerHTML = '<div class="muted">Select a candidate to preview its tags.</div>';
      return;
    }
    if (!cache.has(c.index)) {
      cache.set(c.index, api(`/api/review/${pr.task_id}/tag_preview?index=${c.index}`).catch((err) => ({ error: err.message })));
      chipsEl.innerHTML = "";
      bodyEl.innerHTML = '<div class="muted"><span class="spinner"></span> Comparing tags…</div>';
    }
    const data = await cache.get(c.index);
    if (current !== c) return;
    if (data.error) {
      cache.delete(c.index);
      chipsEl.innerHTML = "";
      bodyEl.innerHTML = `<div class="muted">Couldn't preview tags: ${escapeHtml(data.error)}</div>`;
      return;
    }
    chipsEl.innerHTML = tagPreviewChips(data);
    renderTagPreview(bodyEl, data);
  }
  return { focusCandidate };
}

async function openReview(pr) {
  if (pr.kind === "duplicate") return openDuplicateReview(pr);

  const container = document.createElement("div");
  container.innerHTML = `<h3>${escapeHtml(pr.path)}</h3>`;
  const purchase = pr.payload.purchase;
  if (purchase) {
    const note = document.createElement("div");
    note.className = "muted purchase-note";
    const store = { itunes: "iTunes", amazon: "Amazon" }[purchase.store] || purchase.store;
    note.textContent = `${store} purchase` +
      (purchase.added ? `: added ${purchase.added} digital release${purchase.added === 1 ? "" : "s"} of this album to the candidates.` : ".") +
      (purchase.year ? ` Releases marked "likely your purchase" are digital and from ${purchase.year}, like your files.` : "");
    container.appendChild(note);
  }
  const artHost = document.createElement("div");
  container.appendChild(artHost);
  const list = document.createElement("div");
  container.appendChild(list);
  const tagHost = document.createElement("div");
  container.appendChild(tagHost);
  const artChoice = createArtChoiceCard(artHost, pr);
  const tagPreview = createTagPreviewSection(tagHost, pr);

  let focusedIndex = null;

  function renderCandidates() {
    list.innerHTML = "";
    pr.payload.candidates.forEach((c, i) => {
      const div = document.createElement("div");
      div.className = "candidate" + (focusedIndex === i ? " focused" : "");
      const artistAlbum = c.album ? `${c.artist} – ${c.album}` : `${c.artist} – ${c.title}`;
      div.innerHTML = `
        <div>${escapeHtml(artistAlbum)} ${c.year ? `(${c.year})` : ""}
          ${c.looks_purchased ? '<span class="badge purchased" title="Digital release from the same year as your files">likely your purchase</span>' : ""}</div>
        <div class="dist">distance ${c.distance} · ${escapeHtml(c.data_source || "?")}${[c.media, c.country, c.tracks ? `${c.tracks.length} tracks` : ""].filter(Boolean).map((s) => " · " + escapeHtml(s)).join("")}</div>
        <div class="row">
          <button data-select>Select</button>
        </div>`;
      div.addEventListener("click", () => {
        if (focusedIndex !== i) {
          focusedIndex = i;
          renderCandidates();
          artChoice.focusCandidate(c);
          tagPreview.focusCandidate(c);
        }
      });
      div.querySelector("[data-select]").addEventListener("click", async (e) => {
        e.stopPropagation();
        const toast = createProgressToast(`Applying import for ${pr.path}…`);
        try {
          await decide(pr.task_id, { action: "select", index: c.index, art_choice: artChoice.choice() });
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
  }
  artChoice.focusCandidate(pr.payload.candidates[0] || null);
  tagPreview.focusCandidate(pr.payload.candidates[0] || null);

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
      await decide(pr.task_id, { action: "asis", art_choice: artChoice.choice({ asis: true }) });
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
  container.parentElement.classList.add("modal-wide");
}

// Album art for an import. Shows what the files have now ("keep") and the
// options for after import: the selected release's Cover Art Archive art,
// iTunes Store art (iTunes purchases), or an image file in the inbox
// folder. Images come from the server (/api/art/<sha1>, cached forever),
// which applies the choice on import. Default, mirrored from
// artchoice.default_choice: folder image, else iTunes art, else the larger
// of the files' art and the Cover Art Archive art.
function createArtChoiceCard(host, pr) {
  let options = null;       // /api/inbox/art_options
  let candidate = null;     // focused candidate
  const caa = {};           // album_id -> /api/coverart/candidate result (or {state: "loading"})
  let selected = null;
  let touched = false;

  const area = (x) => (x && x.width && x.height ? x.width * x.height : 0);
  const size = (x) => [x && x.width && x.height ? `${x.width} × ${x.height} px` : "", x && x.bytes ? explorerBytes(x.bytes) : ""].filter(Boolean).join(" · ");

  function current() { return candidate ? caa[candidate.album_id] : null; }

  function defaultChoice() {
    if (options.folder) return "folder";
    if (options.itunes && options.itunes.image_url) return "itunes";
    const c = current();
    if (c && c.state === "ok" && (!options.keep || area(c) > area(options.keep))) return "candidate";
    if (c && c.state === "loading" && !options.keep) return "candidate";
    return "keep";
  }

  function tiles() {
    const out = [];
    const k = options.keep;
    out.push({ value: "keep", title: "Keep current art", url: k && k.image_url,
      detail: k ? size(k) + (k.tracks_with_this_art < k.tracks_total ? ` · on ${k.tracks_with_this_art} of ${k.tracks_total} tracks` : "") : "Your files have no embedded art" });
    if (candidate) {
      const c = current() || { state: "loading" };
      const detail = {
        loading: "loading…",
        none: "No art for this release",
        unavailable: "Couldn't reach the Cover Art Archive",
        ok: size(c) + (c.source === "releasegroup" ? " · from the release group" : ""),
      }[c.state];
      out.push({ value: "candidate", title: "Cover Art Archive", url: c.state === "ok" ? c.image_url : null,
        detail, disabled: c.state === "none" || c.state === "unavailable", retry: c.state === "unavailable" });
    }
    if (options.itunes) {
      const it = options.itunes;
      out.push({ value: "itunes", title: "iTunes Store", url: it.image_url,
        detail: it.image_url ? size(it) : it.error, disabled: !it.image_url });
    }
    if (options.folder) out.push({ value: "folder", title: "Image in the folder", url: options.folder.image_url, detail: `${options.folder.name} · ${size(options.folder)}` });
    return out;
  }

  function note() {
    switch (selected) {
      case "keep": return options.keep ? "Your files keep the art they have now." : "Imported without album art.";
      case "candidate": return "The selected release's front cover is embedded in the imported files.";
      case "itunes": return "The iTunes Store artwork is embedded in the imported files.";
      case "folder": return `${escapeHtml(options.folder.name)} is embedded in the imported files.`;
      default: return "";
    }
  }

  function render() {
    if (!options) { host.innerHTML = `<div class="art-choice"><div class="art-choice-title">Album art</div><div class="muted">Loading…</div></div>`; return; }
    const ts = tiles();
    const usable = ts.filter((x) => !x.disabled).map((x) => x.value);
    if (!touched || !usable.includes(selected)) selected = defaultChoice();
    if (!usable.includes(selected)) selected = "keep";
    host.innerHTML = `
      <div class="art-choice">
        <div class="art-choice-title">Album art after import</div>
        <div class="art-options">${ts.map((o) => `
          <label class="art-option${o.value === selected ? " selected" : ""}${o.disabled ? " disabled" : ""}">
            <input type="radio" name="art-choice-${pr.task_id}" value="${o.value}" ${o.value === selected ? "checked" : ""} ${o.disabled ? "disabled" : ""} data-art-choice />
            <span class="art-thumb">${o.url ? `<img src="${escapeHtml(o.url)}" alt="" data-art-img />` : ""}</span>
            <span class="art-option-text"><b>${o.title}</b><span class="muted">${escapeHtml(o.detail || "")}</span>
              ${o.retry ? '<button class="secondary small" data-art-retry>Retry</button>' : ""}</span>
          </label>`).join("")}
        </div>
        <div class="muted art-choice-note">${note()}</div>
      </div>`;
    host.querySelectorAll("[data-art-choice]").forEach((r) => r.addEventListener("change", () => {
      selected = r.value; touched = true; render();
    }));
    host.querySelectorAll("[data-art-img]").forEach((img) => img.addEventListener("error", () => {
      img.replaceWith(Object.assign(document.createElement("span"), { className: "muted art-broken", textContent: "couldn't load" }));
    }));
    host.querySelector("[data-art-retry]")?.addEventListener("click", (e) => {
      e.preventDefault();
      delete caa[candidate.album_id];
      loadCaa(candidate);
    });
  }

  async function loadCaa(c) {
    if (!c || !c.album_id || caa[c.album_id]) return;
    caa[c.album_id] = { state: "loading" };
    render();
    try {
      const q = new URLSearchParams({ release: c.album_id, releasegroup: c.releasegroup_id || "" });
      caa[c.album_id] = await api(`/api/coverart/candidate?${q}`);
    } catch {
      caa[c.album_id] = { state: "unavailable" };
    }
    render();
  }

  render();
  api(`/api/inbox/art_options?path=${encodeURIComponent(pr.path)}`)
    .then((o) => { options = o; render(); })
    .catch(() => { options = { keep: null, folder: null, itunes: null }; render(); });

  return {
    focusCandidate(c) { candidate = c; render(); loadCaa(c); },
    // Sent with the decision; null lets the server apply its default.
    // "Use as-is" has no release, so Cover Art Archive art isn't an option.
    choice({ asis = false } = {}) {
      if (!options || !selected) return null;
      return asis && selected === "candidate" ? "keep" : selected;
    },
  };
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
      ${pendingBadgeHtml(a.pending_move)}
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
  watchPendingMoves(albums.filter((a) => a.pending_move === "waiting").map((a) => a.id), q);
  renderMisplacedBar(q);
}

// "waiting": tags were just written; the move follows a Navidrome scan.
// "misplaced": files found away from their computed path (at startup, or a
// failed move); they stay until "Move now" / "Move all".
function pendingBadgeHtml(state) {
  if (state === "waiting") return `<span class="pending-badge" title="${PENDING_MOVE_HINT}">Waiting for Navidrome</span>`;
  if (state === "misplaced") return `<span class="pending-badge misplaced" title="${MISPLACED_HINT}">Not at expected path</span>`;
  return "";
}

const MISPLACED_HINT =
  "These files aren't where your beets path settings would put them (usually named under older rules). They stay put until you use Move now or Move all.";

async function renderMisplacedBar(q) {
  const bar = $("#misplaced-bar");
  let pending;
  try {
    pending = (await api("/api/library/pending_moves")).pending.filter((p) => !p.auto);
  } catch (_) {
    return;
  }
  bar.hidden = pending.length === 0;
  if (!pending.length) return;
  const albums = pending.filter((p) => p.kind === "album").length;
  const singles = pending.length - albums;
  const what = [albums && plural(albums, "album"), singles && plural(singles, "single track")].filter(Boolean).join(" and ");
  bar.innerHTML = `
    <div><strong>${what}</strong> ${pending.length === 1 ? "isn't" : "aren't"} at the path your beets settings give ${pending.length === 1 ? "it" : "them"}.</div>
    <div class="muted">Moving only renames files; tags don't change, so Navidrome keeps play counts and playlists.</div>
    <button data-move-all>Move all…</button>`;
  bar.querySelector("[data-move-all]").addEventListener("click", () => confirmMoveAll(what, q));
}

function confirmMoveAll(what, q) {
  const body = document.createElement("div");
  body.innerHTML = `
    <h3>Move ${what} to their expected paths?</h3>
    <p class="muted">Files are renamed to match your beets path settings (for example <span class="mono">AC-DC</span> becomes <span class="mono">AC_DC</span>).
    Albums still waiting for a Navidrome scan are left alone; they move by themselves.</p>
    <div class="row">
      <button data-confirm>Move all</button>
      <button class="secondary" data-cancel>Cancel</button>
    </div>`;
  const modal = openModal(body);
  body.querySelector("[data-cancel]").addEventListener("click", () => modal.close());
  body.querySelector("[data-confirm]").addEventListener("click", async (e) => {
    e.target.disabled = true;
    e.target.textContent = "Moving…";
    try {
      const res = await api("/api/library/pending_moves/move_all", { method: "POST" });
      modal.close();
      if (res.failed.length) showToast(`Moved ${res.moved}; ${res.failed.length} failed (see the album pages).`, "error");
      else showToast(`Moved ${plural(res.moved, "album")}.`, "success");
      loadLibrary(q);
    } catch (err) {
      e.target.disabled = false;
      e.target.textContent = "Move all";
      showToast(`Move failed: ${err.message}`, "error");
    }
  });
}

// Pending Move (ADR-0011): files of an album whose tags were just written
// move once Navidrome has scanned the new tags. While any shown album
// waits, re-check every few seconds and refresh the grid when it's done.
const PENDING_MOVE_HINT =
  "New tags are written; the files move to their new path once Navidrome has scanned them, so play counts and playlists carry over.";
let pendingMoveTimer = null;
function watchPendingMoves(albumIds, q) {
  clearTimeout(pendingMoveTimer);
  if (albumIds.length === 0) return;
  pendingMoveTimer = setTimeout(async () => {
    let still;
    try {
      const res = await api("/api/library/pending_moves");
      still = new Set(res.pending.filter((p) => p.kind === "album").map((p) => p.id));
    } catch (_) {
      return watchPendingMoves(albumIds, q);
    }
    if (albumIds.some((id) => !still.has(id))) loadLibrary(q);
    else watchPendingMoves(albumIds, q);
  }, 3000);
}

function savedMessage(res, what) {
  return res && (res.move === "pending" || res.pending)
    ? `${what} Files move once Navidrome has scanned the new tags.`
    : what;
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
      const res = await api("/api/library/albums/bulk_fields", {
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
        showToast(savedMessage(res, `Updated navidrome_library on ${albumIds.length} album(s).`), "success");
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

// Undo import (restore.py): dry run first, then an explicit confirm.
async function showUndoImportPanel(panel, albumId, detail, onDone) {
  panel.hidden = false;
  panel.innerHTML = '<div class="muted"><span class="spinner"></span> Checking the original files…</div>';
  let plan;
  try {
    plan = await api(`/api/library/albums/${albumId}/undo_import`);
  } catch (err) {
    panel.innerHTML = `<div class="explorer-warn">Couldn't check: ${escapeHtml(err.message)}</div>`;
    return;
  }
  const top = plan.folders.filter((f) => !plan.folders.some((g) => g !== f && f.startsWith(g + "/")));
  const folders = top.map((f) => `<div class="mono">${escapeHtml(f)}</div>`).join("");
  if (!plan.ok) {
    panel.innerHTML = `
      <div class="explorer-warn">This album can't be undone exactly, so nothing will be changed:</div>
      <ul class="undo-problems">${plan.problems.map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul>
      <div class="row"><button class="secondary" data-undo-cancel>Close</button></div>`;
    panel.querySelector("[data-undo-cancel]").addEventListener("click", () => { panel.hidden = true; });
    return;
  }
  const n = plan.files.length;
  const present = plan.already_in_inbox;
  panel.innerHTML = `
    <div><strong>Undo import of ${escapeHtml(detail.fields.album)}?</strong></div>
    <div class="muted">
      ${plan.audio_files === 1 ? "The original track goes" : `The ${plan.audio_files} original tracks go`}${plan.other_files ? ` (and ${plan.other_files} other file${plan.other_files === 1 ? "" : "s"} from the folder)` : ""}
      back to the inbox exactly as before import (same tags, art and checksums), and the album is removed from the library,
      including its files in the music folder.
      ${present === n ? (n === 1 ? " It's already in the inbox unchanged, so it's left as it is." : " They're already in the inbox unchanged, so they're left as they are.")
        : present ? ` ${present} of them ${present === 1 ? "is" : "are"} already in the inbox unchanged and left as ${present === 1 ? "it is" : "they are"}.` : ""}
    </div>
    <div class="muted">Back to:</div>${folders}
    <div class="row">
      <button class="danger" data-undo-confirm>Undo import</button>
      <button class="secondary" data-undo-cancel>Cancel</button>
    </div>`;
  panel.querySelector("[data-undo-cancel]").addEventListener("click", () => { panel.hidden = true; });
  panel.querySelector("[data-undo-confirm]").addEventListener("click", async (e) => {
    e.target.disabled = true;
    const toast = createProgressToast(`Undoing import of ${detail.fields.album}…`);
    try {
      const r = await api(`/api/library/albums/${albumId}/undo_import`, { method: "POST" });
      toast.done(`Undone: ${r.audio_files} track${r.audio_files === 1 ? "" : "s"}${r.other_files ? ` and ${r.other_files} other file${r.other_files === 1 ? "" : "s"}` : ""} back in the inbox.`);
      onDone();
    } catch (err) {
      e.target.disabled = false;
      toast.error(`Undo failed (nothing was changed): ${err.message}`);
    }
  });
}

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
      <button class="secondary danger" data-undo-import>Undo import…</button>
    </div>
    ${detail.pending_move ? `
    <div class="pending-move-banner" data-pending-move>
      <span><strong>Files not moved yet:</strong> ${escapeHtml(detail.pending_move.reason)}.</span>
      <button class="secondary" data-move-now>Move now</button>
    </div>` : ""}
    <div class="undo-panel" data-undo-panel hidden></div>
    <div data-explorer></div>`;

  const saveAlbumWithConflict = async (conflictResolution = null) => {
    const value = container.querySelector('[data-field="navidrome_library"]').value;
    try {
      const res = await api(`/api/library/albums/${albumId}/fields`, {
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
        showToast(savedMessage(res, "Album saved."), "success");
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

  const moveNowBtn = container.querySelector("[data-move-now]");
  if (moveNowBtn) {
    moveNowBtn.addEventListener("click", async () => {
      const ok = confirm(
        "Move the files now, without waiting for Navidrome?\n\n" +
          "If Navidrome hasn't scanned the new tags yet, these tracks may lose their play counts, stars and playlist entries there."
      );
      if (!ok) return;
      try {
        await api(`/api/library/pending_moves/${detail.pending_move.kind}/${detail.pending_move.id}/move`, { method: "POST" });
        showToast("Files moved.", "success");
        backdrop.close();
        loadLibrary($("#lib-search").value);
      } catch (err) {
        showToast(`Move failed: ${err.message}`, "error");
      }
    });
  }

  container.querySelector("[data-reimport]").addEventListener("click", () => {
    backdrop.close();
    openReimport([albumId]);
  });

  container.querySelector("[data-undo-import]").addEventListener("click", () => {
    showUndoImportPanel(container.querySelector("[data-undo-panel]"), albumId, detail, () => {
      backdrop.close();
      loadLibrary($("#lib-search").value);
      loadInbox();
    });
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

// -- Backfill (ADR-0016): store downloads of tracks already in the library --
let backfillState = null;
let backfillPolling = false;
let backfillSeenApply = null;

const plural = (n, word, words = word + "s") => `${n} ${n === 1 ? word : words}`;

function backfillSummary(c) {
  const parts = [];
  if (c.attach) parts.push(`${c.attach} identical`);
  if (c.replace) parts.push(`${c.replace} to swap in`);
  if (c.keep_library) parts.push(`${c.keep_library} where the library copy is better`);
  if (c.already_saved) parts.push(`${c.already_saved} already saved`);
  if (c.duplicate) parts.push(plural(c.duplicate, "duplicate"));
  if (c.new) parts.push(`${c.new} new`);
  if (c.unreadable) parts.push(`${c.unreadable} unreadable`);
  return parts.join(" · ");
}

function backfillLineHtml(path) {
  const r = backfillState?.results?.[path];
  if (!r) return "";
  const matched = r.tracks.length - (r.counts.new || 0) - (r.counts.unreadable || 0);
  if (!matched) return "";
  const albums = r.albums.map((a) => escapeHtml(a.album)).join("; ");
  return `
    <div class="backfill-line">
      <span class="badge imported">In library</span> ${albums}
      <div class="muted">${escapeHtml(backfillSummary(r.counts))}</div>
      ${r.actionable ? '<button class="secondary" data-backfill>Attach to library…</button>' : ""}
    </div>`;
}

function renderBackfillBar() {
  const bar = $("#backfill-bar");
  const st = backfillState;
  if (!st) {
    bar.innerHTML = "";
    return;
  }
  if (st.running) {
    const n = st.total ? ` ${st.done} / ${st.total}` : "";
    bar.innerHTML = `<div class="backfill-bar"><span class="spinner"></span> ${escapeHtml(st.phase || "Working")}…${n}</div>`;
    pollBackfill();
    return;
  }
  const results = Object.entries(st.results || {});
  const actionable = results.filter(([, r]) => r.actionable).map(([p]) => p);
  const totals = {};
  results.forEach(([, r]) => Object.entries(r.counts).forEach(([k, v]) => (totals[k] = (totals[k] || 0) + v)));
  bar.innerHTML = `
    <div class="backfill-bar">
      <div class="row">
        <button class="secondary" data-backfill-scan>${st.scanned_at ? "Check again" : "Check inbox against library"}</button>
        ${actionable.length ? `<button data-backfill-all>Attach all (${plural(actionable.length, "folder")})…</button>` : ""}
      </div>
      <div class="muted">${st.scanned_at
        ? `Last check: ${escapeHtml(backfillSummary(totals)) || "nothing in the inbox"}.`
        : "Finds store downloads of tracks already in your library: saves them as the tracks' originals (for Undo import) and swaps in better-quality files."}</div>
      ${st.fpcalc ? "" : '<div class="explorer-warn">fpcalc isn\'t installed: only byte-identical audio can be matched.</div>'}
      ${st.error ? `<div class="explorer-warn">The last run failed: ${escapeHtml(st.error)}</div>` : ""}
    </div>`;
  bar.querySelector("[data-backfill-scan]").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      await api("/api/backfill/scan", { method: "POST" });
      loadInbox();
    } catch (err) {
      e.target.disabled = false;
      showToast(err.message, "error");
    }
  });
  bar.querySelector("[data-backfill-all]")?.addEventListener("click", () => openBackfillModal(actionable));
}

async function pollBackfill() {
  if (backfillPolling) return;
  backfillPolling = true;
  try {
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      backfillState = await api("/api/backfill");
      if (!backfillState.running) break;
      renderBackfillBar();
    }
  } catch {
    // next loadInbox() retries
  } finally {
    backfillPolling = false;
  }
  const s = backfillState?.last_apply;
  if (s && s !== backfillSeenApply && backfillState.kind === "apply") {
    backfillSeenApply = s;
    const msg = `Attached: ${plural(s.attached, "identical track")}, ${plural(s.replaced, "track")} swapped for the download.`;
    if (s.errors.length) showToast(`${msg} ${plural(s.errors.length, "problem")}: ${s.errors.join("; ")}`, "error", 12000);
    else showToast(msg, "info", 6000);
  }
  loadInbox();
}

const BF_ACTION = {
  attach: ["Save as original", "Identical audio: the library file isn't touched."],
  replace: ["Swap in", ""],
  keep_library: ["Leave", ""],
  already_saved: ["Leave", ""],
  duplicate: ["Leave", ""],
  new: ["Import later", "Not in the library: import it as usual."],
  unreadable: ["Leave", ""],
};

function openBackfillModal(paths) {
  const results = paths.map((p) => backfillState?.results?.[p]).filter(Boolean);
  const body = document.createElement("div");
  const rows = results.map((r) => `
    <h4 class="mono">${escapeHtml(r.path)}</h4>
    <table class="bf-table">
      <tr><th>Download</th><th>Library track</th><th>Quality</th><th>What happens</th></tr>
      ${r.tracks.map((t) => {
        const [label, why] = BF_ACTION[t.action] || [t.action, ""];
        const name = t.path.split("/").pop();
        const quality = t.library ? `${escapeHtml(t.library)} → ${escapeHtml(t.download)}` : escapeHtml(t.download);
        return `<tr class="bf-${t.action}">
          <td>${escapeHtml(name)}</td>
          <td>${t.title ? `${escapeHtml(t.title)}<div class="muted">${escapeHtml(t.album)}</div>` : '<span class="muted">—</span>'}</td>
          <td>${quality}</td>
          <td><strong>${label}</strong><div class="muted">${escapeHtml(t.note || why)}</div></td>
        </tr>`;
      }).join("")}
    </table>`).join("");
  const n = results.reduce((a, r) => a + (r.counts.attach || 0) + (r.counts.replace || 0), 0);
  body.innerHTML = `
    <h3>Attach ${plural(n, "download")} to your library</h3>
    <div class="muted">
      Each download is saved as its library track's original, so Undo import gives back the file exactly as downloaded.
      <strong>Swap in</strong> replaces the library file with the download, with the library's tags and art written onto it
      (Navidrome keeps play counts and playlists); the old file is kept in <span class="mono">webimport-replaced</span>.
      Used downloads leave the inbox; everything else stays.
    </div>
    ${rows}
    <div class="row">
      <button data-bf-confirm>Attach</button>
      <button class="secondary" data-bf-cancel>Cancel</button>
    </div>`;
  const modal = openModal(body);
  modal.querySelector(".modal").classList.add("modal-wide");
  body.querySelector("[data-bf-cancel]").addEventListener("click", () => modal.close());
  body.querySelector("[data-bf-confirm]").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      await api("/api/backfill/apply", { method: "POST", body: JSON.stringify({ paths }) });
      modal.close();
      loadInbox();
    } catch (err) {
      e.target.disabled = false;
      showToast(err.message, "error");
    }
  });
}

// -- init ---------------------------------------------------------------
loadInbox();
api("/api/version")
  .then((v) => {
    const el = $("#version");
    const tags = v.tags?.length ? ` · ${v.tags.join(", ")}` : "";
    const date = v.date ? ` · ${v.date.slice(0, 10)}` : "";
    el.textContent = `beets-webimport ${v.label}${tags}${date}`;
    el.title = v.commit ? `commit ${v.commit}` : "commit unknown";
  })
  .catch(() => {});
setInterval(() => {
  if ($("#tab-inbox")?.classList.contains("active")) loadInbox();
}, 5000);

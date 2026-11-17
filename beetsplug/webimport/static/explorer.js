// Read-only metadata explorer for a library album.
//
// Left: tree of Album -> (Disc) -> Tracks. Right: every field beets stores
// for the selected node, grouped. Discrepancies between the beets DB and
// the tags actually written in each file (what Navidrome reads) are
// marked with an icon whose tooltip/tap shows both values.
//
// Uses helpers from app.js: api, escapeHtml, showToast, attachLongPress,
// promptApplyTag.

const EXPLORER_GROUPS = [
  ["Core", ["title", "artist", "artists", "album", "albumartist", "albumartists",
    "track", "tracktotal", "disc", "disctotal", "disctitle", "year", "month", "day",
    "genres", "style", "comp", "media", "language", "script", "subtitle", "grouping",
    "bpm", "initial_key", "comments", "encoder"]],
  ["Release", ["label", "catalognum", "barcode", "asin", "country", "albumstatus",
    "albumtype", "albumtypes", "albumdisambig", "releasegroupdisambig",
    "release_group_title", "original_year", "original_month", "original_day"]],
  ["Credits", ["artist_credit", "artist_sort", "artists_credit", "artists_sort",
    "albumartist_credit", "albumartist_sort", "albumartists_credit", "albumartists_sort",
    "composers", "composer_sort", "lyricists", "arrangers", "remixers", "work", "work_disambig"]],
  ["Identifiers", ["mb_albumid", "mb_releasegroupid", "mb_trackid", "mb_releasetrackid",
    "mb_artistid", "mb_artistids", "mb_albumartistid", "mb_albumartistids", "mb_workid",
    "artists_ids", "composers_ids", "lyricists_ids", "arrangers_ids", "remixers_ids",
    "discogs_albumid", "discogs_artistid", "discogs_labelid", "isrc", "trackdisambig",
    "acoustid_id", "acoustid_fingerprint"]],
  ["Loudness", ["rg_track_gain", "rg_track_peak", "rg_album_gain", "rg_album_peak",
    "r128_track_gain", "r128_album_gain"]],
  ["Lyrics", ["lyrics"]],
];

const EXPLORER_LINKS = {
  mb_albumid: "https://musicbrainz.org/release/",
  mb_releasegroupid: "https://musicbrainz.org/release-group/",
  mb_trackid: "https://musicbrainz.org/recording/",
  mb_releasetrackid: "https://musicbrainz.org/track/",
  mb_artistid: "https://musicbrainz.org/artist/",
  mb_albumartistid: "https://musicbrainz.org/artist/",
  mb_workid: "https://musicbrainz.org/work/",
  discogs_albumid: "https://www.discogs.com/release/",
  acoustid_id: "https://acoustid.org/track/",
};
const EXPLORER_COPYABLE = new Set(["path", "artpath", ...Object.keys(EXPLORER_LINKS), "isrc", "barcode", "catalognum"]);
const EXPLORER_LONG = 140; // chars before a value is collapsed

function explorerIsEmpty(field, v) {
  if (v === null || v === undefined || v === "") return true;
  if (Array.isArray(v)) return v.length === 0;
  if (v === 0 && field !== "comp") return true; // beets uses 0 for "unset" ints
  return false;
}

function explorerFormat(field, v) {
  if (v === null || v === undefined) return "";
  if (Array.isArray(v)) return v.join(", ");
  switch (field) {
    case "length": {
      const s = Math.round(v);
      return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }
    case "added":
    case "mtime":
      return v ? new Date(v * 1000).toLocaleString() : "";
    case "bitrate":
      return `${Math.round(v / 1000)} kbps`;
    case "samplerate":
      return `${(v / 1000).toLocaleString()} kHz`;
    case "bitdepth":
      return `${v}-bit`;
    case "comp":
      return v ? "Yes" : "No";
  }
  return String(v);
}

function explorerSame(a, b) {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
    || (explorerIsEmpty("", a) && explorerIsEmpty("", b));
}

async function renderAlbumExplorer(host, albumId) {
  host.innerHTML = '<div class="muted"><span class="spinner"></span> Loading metadata…</div>';
  let data;
  try {
    data = await api(`/api/library/albums/${albumId}/explore`);
  } catch (err) {
    host.innerHTML = `<div class="muted">Failed to load metadata: ${escapeHtml(err.message)}</div>`;
    return;
  }

  const itemKeys = new Set(data.item_keys);
  const readonly = new Set(data.readonly_fields);
  const tracksById = new Map(data.tracks.map((t) => [t.id, t]));
  const state = {
    selected: { kind: "album" },
    filter: "",
    showEmpty: false,
    fileTags: null, // null = loading, {error} or Map(trackId -> result)
  };

  host.innerHTML = `
    <div class="explorer">
      <nav class="explorer-tree" aria-label="Album contents"></nav>
      <section class="explorer-panel">
        <button class="secondary explorer-back">&larr; Tracks</button>
        <div class="explorer-tools">
          <input type="search" placeholder="Filter fields…" class="explorer-filter" />
          <label class="explorer-empty-toggle"><input type="checkbox" /> Show empty</label>
        </div>
        <div class="explorer-body"></div>
      </section>
    </div>`;
  const root = host.querySelector(".explorer");
  const treeEl = host.querySelector(".explorer-tree");
  const bodyEl = host.querySelector(".explorer-body");

  host.querySelector(".explorer-filter").addEventListener("input", (e) => {
    state.filter = e.target.value.trim().toLowerCase();
    renderPanel();
  });
  host.querySelector(".explorer-empty-toggle input").addEventListener("change", (e) => {
    state.showEmpty = e.target.checked;
    renderPanel();
  });
  host.querySelector(".explorer-back").addEventListener("click", () => {
    root.classList.remove("show-detail");
  });

  // -- file tag discrepancies (fetched after first render) ---------------
  function trackFile(trackId) {
    return state.fileTags instanceof Map ? state.fileTags.get(trackId) : null;
  }
  function trackIssueCount(trackId) {
    const r = trackFile(trackId);
    if (!r) return 0;
    return r.error ? 1 : r.mismatches.length;
  }

  // -- tree --------------------------------------------------------------
  function renderTree() {
    const discs = new Map();
    data.tracks.forEach((t) => {
      const d = t.fields.disc || 1;
      if (!discs.has(d)) discs.set(d, []);
      discs.get(d).push(t);
    });
    const multiDisc = discs.size > 1;
    const totalIssues = data.tracks.reduce((n, t) => n + (trackIssueCount(t.id) ? 1 : 0), 0);
    const a = data.album.fields;

    let html = `<button class="tree-node tree-album ${state.selected.kind === "album" ? "selected" : ""}" data-node="album">
        <span class="tree-label">${escapeHtml(a.album || "(untitled album)")}</span>
        <span class="tree-sub muted">${escapeHtml(a.albumartist || "")}${a.year ? " · " + a.year : ""}</span>
        ${totalIssues ? `<span class="disc-icon" title="${totalIssues} track(s) have file tags that differ from beets">⚠ ${totalIssues}</span>` : ""}
      </button>`;
    for (const [disc, tracks] of [...discs.entries()].sort((x, y) => x[0] - y[0])) {
      if (multiDisc) html += `<div class="tree-disc muted">Disc ${disc}</div>`;
      for (const t of tracks) {
        const f = t.fields;
        const r = trackFile(t.id);
        const file = (f.path || "").split("/").pop();
        const sel = state.selected.kind === "track" && state.selected.id === t.id;
        let icon = "";
        if (r && r.error) icon = `<span class="disc-icon error" title="Couldn't read file: ${escapeHtml(r.error)}">✕</span>`;
        else if (r && r.mismatches.length) icon = `<span class="disc-icon" title="${r.mismatches.length} file tag(s) differ from beets">⚠ ${r.mismatches.length}</span>`;
        html += `<button class="tree-node tree-track ${sel ? "selected" : ""}" data-node="${t.id}">
            <span class="tree-label">${f.track ? String(f.track).padStart(2, "0") + " " : ""}${escapeHtml(f.title || "(untitled)")}</span>
            <span class="tree-sub muted">${escapeHtml(file)}</span>
            ${icon}
          </button>`;
      }
    }
    treeEl.innerHTML = html;
    treeEl.querySelectorAll("[data-node]").forEach((btn) => {
      const nodeId = btn.dataset.node;
      btn.addEventListener("click", () => {
        state.selected = nodeId === "album" ? { kind: "album" } : { kind: "track", id: Number(nodeId) };
        root.classList.add("show-detail");
        renderTree();
        renderPanel();
      });
      if (nodeId !== "album" && typeof attachLongPress === "function") {
        attachLongPress(btn, () => [
          { label: "Apply tag…", onClick: () => promptApplyTag("item", Number(nodeId)) },
        ]);
      }
    });
  }

  // -- panel -------------------------------------------------------------
  function fieldAnnotations(field, node) {
    // Returns {cls, badges[], detail?} for one field row.
    const out = { cls: "", badges: [] };
    if (state.selected.kind === "album") {
      if (itemKeys.has(field)) {
        const albumVal = node.fields[field];
        const differing = data.tracks.filter((t) => !explorerSame(t.fields[field], albumVal));
        if (differing.length) {
          const vals = differing.map((t) => `#${t.fields.track || "?"}: ${explorerFormat(field, t.fields[field]) || "(empty)"}`);
          out.badges.push(`<span class="field-badge varies" title="Tracks that differ from the album:\n${escapeHtml(vals.join("\n"))}">varies (${differing.length})</span>`);
        }
      }
      // Album-level fields are written into every track's file tags.
      if (state.fileTags instanceof Map) {
        const lines = [];
        for (const t of data.tracks) {
          const m = trackFile(t.id)?.mismatches.find((x) => x.field === field);
          if (m) lines.push(`#${t.fields.track || "?"} — beets DB: ${explorerFormat(field, m.db) || "(empty)"} | file tag: ${explorerFormat(field, m.file) || "(empty)"}`);
        }
        if (lines.length) {
          out.badges.push(discButton(`${lines.length} track file(s) differ from beets`, lines.join("\n")));
        }
      }
    } else {
      const track = tracksById.get(state.selected.id);
      if (itemKeys.has(field)) {
        if (explorerSame(track.fields[field], data.album.fields[field])) out.cls = "inherited";
        else out.badges.push(`<span class="field-badge override" title="Album value: ${escapeHtml(explorerFormat(field, data.album.fields[field]) || "(empty)")}">differs from album</span>`);
      }
      const r = trackFile(track.id);
      const m = r?.mismatches.find((x) => x.field === field);
      if (m) {
        out.badges.push(discButton("File tag differs from beets",
          `beets DB: ${explorerFormat(field, m.db) || "(empty)"}\nfile tag: ${explorerFormat(field, m.file) || "(empty)"}`));
      }
      if (r?.unsupported.includes(field)) {
        out.badges.push(`<span class="field-badge unsupported" title="This file format has no tag for this field, so the value lives only in beets' database.">not in file</span>`);
      }
    }
    return out;
  }

  function discButton(label, detail) {
    return `<button class="disc-icon" data-disc-detail="${escapeHtml(detail)}" title="${escapeHtml(label + ":\n" + detail)}" aria-label="${escapeHtml(label)}">⚠</button>`;
  }

  function renderValue(field, v) {
    const text = explorerFormat(field, v);
    const raw = typeof v === "object" ? JSON.stringify(v) : String(v ?? "");
    let inner;
    if (EXPLORER_LINKS[field] && typeof v === "string" && v) {
      inner = `<a href="${EXPLORER_LINKS[field]}${encodeURIComponent(v)}" target="_blank" rel="noopener">${escapeHtml(text)}</a>`;
    } else if (EXPLORER_LINKS[field] && typeof v === "number" && v) {
      inner = `<a href="${EXPLORER_LINKS[field]}${v}" target="_blank" rel="noopener">${escapeHtml(text)}</a>`;
    } else if (text.length > EXPLORER_LONG) {
      inner = `<span class="long-value">${escapeHtml(text.slice(0, EXPLORER_LONG))}…</span> <button class="link-btn" data-expand>show all</button>`;
    } else {
      inner = escapeHtml(text);
    }
    const copy = EXPLORER_COPYABLE.has(field) && text ? `<button class="link-btn" data-copy="${escapeHtml(raw)}" title="Copy">copy</button>` : "";
    return `<span class="field-value" title="${escapeHtml(raw)}" data-full="${text.length > EXPLORER_LONG ? escapeHtml(text) : ""}">${inner}</span>${copy}`;
  }

  function renderPanel() {
    const node = state.selected.kind === "album" ? data.album : tracksById.get(state.selected.id);
    const fields = node.fields;
    const custom = new Set(node.custom_fields);
    const placed = new Set();
    const groups = [];
    for (const [name, list] of EXPLORER_GROUPS) {
      groups.push([name, list.filter((f) => f in fields && !custom.has(f))]);
      list.forEach((f) => placed.add(f));
    }
    groups.push(["Custom fields", [...custom].sort()]);
    groups.push(["Audio & file (read-only)", [...readonly].filter((f) => f in fields)]);
    readonly.forEach((f) => placed.add(f));
    groups.push(["Other", Object.keys(fields).filter((f) => !placed.has(f) && !custom.has(f)).sort()]);

    let header;
    if (state.selected.kind === "album") {
      header = `<h4>Album</h4><p class="muted explorer-note">Album fields are copied onto every track and written into each file. “varies” means some tracks hold a different value.</p>`;
    } else {
      const r = trackFile(node.id);
      header = `<h4>Track ${escapeHtml(String(fields.track || ""))}: ${escapeHtml(fields.title || "")}</h4>
        <p class="muted explorer-note">Dimmed fields match the album.</p>
        ${r?.modified_outside_beets ? `<p class="explorer-warn">⚠ This file was modified after beets last read or wrote it.</p>` : ""}
        ${r?.error ? `<p class="explorer-warn">✕ Couldn't read file tags: ${escapeHtml(r.error)}</p>` : ""}`;
    }
    header += fileTagSummary();

    let html = header;
    let shown = 0;
    for (const [name, list] of groups) {
      const rows = list
        .filter((f) => state.showEmpty || !explorerIsEmpty(f, fields[f]) || fieldAnnotations(f, node).badges.length)
        .filter((f) => !state.filter || f.toLowerCase().includes(state.filter)
          || explorerFormat(f, fields[f]).toLowerCase().includes(state.filter))
        .map((f) => {
          const ann = fieldAnnotations(f, node);
          shown++;
          return `<div class="field-row ${ann.cls}">
              <span class="field-name">${escapeHtml(f)}</span>
              <span class="field-val-wrap">${renderValue(f, fields[f])} ${ann.badges.join(" ")}</span>
              <div class="disc-detail" hidden></div>
            </div>`;
        });
      if (rows.length) html += `<h5 class="field-group">${escapeHtml(name)}</h5>${rows.join("")}`;
    }
    if (!shown) html += `<p class="muted">No fields match.</p>`;
    bodyEl.innerHTML = html;

    bodyEl.querySelectorAll("[data-disc-detail]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const detailEl = btn.closest(".field-row").querySelector(".disc-detail");
        detailEl.hidden = !detailEl.hidden;
        detailEl.textContent = btn.dataset.discDetail;
      });
    });
    bodyEl.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(btn.dataset.copy);
          showToast("Copied", "success", 1500);
        } catch {
          showToast("Copy failed (clipboard needs HTTPS or localhost)", "error");
        }
      });
    });
    bodyEl.querySelectorAll("[data-expand]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const val = btn.parentElement.querySelector(".field-value");
        val.textContent = val.dataset.full;
        val.classList.add("expanded");
        btn.remove();
      });
    });
  }

  function fileTagSummary() {
    if (state.fileTags === null) return `<p class="muted explorer-note"><span class="spinner"></span> Checking file tags…</p>`;
    if (state.fileTags.error) return `<p class="explorer-warn">Couldn't check file tags: ${escapeHtml(state.fileTags.error)}</p>`;
    if (state.selected.kind === "album") {
      const bad = data.tracks.filter((t) => trackIssueCount(t.id)).length;
      return bad
        ? `<p class="explorer-warn">⚠ ${bad} of ${data.tracks.length} tracks have file tags that differ from beets' database. Tap ⚠ for details.</p>`
        : `<p class="explorer-ok">✓ All file tags match beets' database.</p>`;
    }
    const r = trackFile(state.selected.id);
    if (!r || r.error) return "";
    return r.mismatches.length
      ? `<p class="explorer-warn">⚠ ${r.mismatches.length} file tag(s) differ from beets' database.</p>`
      : `<p class="explorer-ok">✓ File tags match beets' database.</p>`;
  }

  renderTree();
  renderPanel();

  try {
    const ft = await api(`/api/library/albums/${albumId}/filetags`);
    state.fileTags = new Map(ft.tracks.map((t) => [t.id, t]));
  } catch (err) {
    state.fileTags = { error: err.message };
  }
  if (!host.isConnected) return; // modal closed meanwhile
  renderTree();
  renderPanel();
}

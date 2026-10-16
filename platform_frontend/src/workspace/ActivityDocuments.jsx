import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import "./activity-documents.css";

export const documentKey = (file) =>
  String(
    file.document_id ||
      file.id ||
      file.storageKey ||
      `${file.name}:${file.size}`,
  );
const sameFile = (a, b) =>
  documentKey(a) === documentKey(b) || (a.name === b.name && a.size === b.size);
const fileSize = (file) => `${Math.max(1, Math.ceil(file.size / 1024))} KB`;
const reducedMotion = () =>
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** The activity's controlled selection; the parent retains all persistence/submission. */
export default function ActivityDocuments({
  library,
  selected,
  onChange,
  onUpload,
  onContinue,
}) {
  const [tab, setTab] = useState("existing");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const selection = useRef(selected);
  selection.current = selected;
  const rows = useRef(new Map());
  const pending = useRef(new Map());
  const before = useRef(new Map());
  const flights = useRef(new Map());
  const animations = useRef(new Set());
  const stack = useRef(null);
  const uploadInput = useRef(null);
  const uploadButton = useRef(null);
  const tabButtons = useRef({});
  const alive = useRef(true);

  const stopFlight = (key) => {
    const flight = flights.current.get(key);
    if (!flight) return;
    flights.current.delete(key);
    flight.animation.cancel();
    flight.clone.remove();
    flight.row.style.visibility = "";
  };
  const stopAll = () => {
    [...flights.current.keys()].forEach(stopFlight);
    animations.current.forEach((animation) => animation.cancel());
    animations.current.clear();
  };
  useEffect(() => {
    alive.current = true;
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const onPreference = () => {
      if (media?.matches) stopAll();
    };
    const onScroll = () => [...flights.current.keys()].forEach(stopFlight);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    window.visualViewport?.addEventListener("resize", onScroll);
    media?.addEventListener("change", onPreference);
    return () => {
      alive.current = false;
      stopAll();
      pending.current.clear();
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
      window.visualViewport?.removeEventListener("resize", onScroll);
      media?.removeEventListener("change", onPreference);
    };
  }, []);

  const rememberPositions = () => {
    before.current = new Map(
      [...rows.current].map(([key, row]) => [key, row.getBoundingClientRect()]),
    );
  };
  const commit = (next) => {
    selection.current = next;
    onChange(next);
  };
  const add = (file, source) => {
    if (selection.current.some((item) => sameFile(item, file))) return;
    rememberPositions();
    const key = documentKey(file);
    pending.current.set(key, {
      source: source?.getBoundingClientRect(),
      count: selection.current.length,
    });
    commit([...selection.current, file]);
  };
  const remove = (file) => {
    rememberPositions();
    const key = documentKey(file);
    pending.current.delete(key);
    stopFlight(key);
    commit(selection.current.filter((item) => !sameFile(item, file)));
  };
  const clearAll = () => {
    stopAll();
    pending.current.clear();
    before.current.clear();
    commit([]);
  };
  const trackAnimation = (animation) => {
    animations.current.add(animation);
    animation.finished
      .catch(() => {})
      .finally(() => animations.current.delete(animation));
  };

  useLayoutEffect(() => {
    const activeKeys = new Set(selected.map(documentKey));
    [...flights.current.keys()]
      .filter((key) => !activeKeys.has(key))
      .forEach(stopFlight);
    const additions = [...pending.current].filter(([key]) =>
      activeKeys.has(key),
    );
    // Only the selected-list scroll position changes; never scroll the page for motion.
    if (additions.length && selected.length > 4 && stack.current) {
      stack.current.scrollTop = stack.current.scrollHeight;
    }
    // Batch all destination/reflow reads before creating clones or animations.
    const positions = new Map(
      [...rows.current].map(([key, row]) => [key, row.getBoundingClientRect()]),
    );
    const vv = window.visualViewport;
    const viewport = {
      top: vv?.offsetTop || 0,
      left: vv?.offsetLeft || 0,
      height: vv?.height || window.innerHeight,
      width: vv?.width || window.innerWidth,
    };
    const visible = (rect) =>
      rect &&
      rect.top >= viewport.top &&
      rect.bottom <= viewport.top + viewport.height &&
      rect.left >= viewport.left &&
      rect.right <= viewport.left + viewport.width;
    const canAnimate = !reducedMotion();
    for (const [key, rect] of positions) {
      const previous = before.current.get(key),
        row = rows.current.get(key);
      if (
        canAnimate &&
        row?.animate &&
        previous &&
        !pending.current.has(key) &&
        !flights.current.has(key)
      ) {
        const delta = previous.top - rect.top;
        if (Math.abs(delta) > 1 && Math.abs(delta) < viewport.height) {
          trackAnimation(
            row.animate(
              [
                { transform: `translateY(${delta}px)` },
                { transform: "translateY(0)" },
              ],
              { duration: 200, easing: "cubic-bezier(.2,.7,.2,1)" },
            ),
          );
        }
      }
    }
    before.current.clear();
    for (const [key, entry] of additions) {
      pending.current.delete(key);
      const row = rows.current.get(key),
        target = positions.get(key);
      if (!row || !target) continue;
      row.dataset.selectionMotion = "none";
      if (!canAnimate || !row.animate) continue;
      const source = entry.source;
      const distance = source ? target.top - source.top : Infinity;
      const fly =
        entry.count < 4 &&
        visible(source) &&
        visible(target) &&
        distance > 4 &&
        distance < Math.min(650, viewport.height * 0.85);
      if (!fly) {
        row.dataset.selectionMotion = "entrance";
        trackAnimation(
          row.animate(
            [
              { opacity: 0.25, transform: "translateY(5px)" },
              { opacity: 1, transform: "translateY(0)" },
            ],
            { duration: 150, easing: "cubic-bezier(.2,.7,.2,1)" },
          ),
        );
        continue;
      }
      const file = selected.find((item) => documentKey(item) === key);
      row.dataset.selectionMotion = "flight";
      const clone = document.createElement("div");
      clone.className = "ad-flying-document";
      clone.setAttribute("aria-hidden", "true");
      clone.inert = true;
      const name = document.createElement("strong"),
        size = document.createElement("span");
      name.textContent = file.name;
      size.textContent = fileSize(file);
      clone.append(name, size);
      Object.assign(clone.style, {
        left: `${source.left}px`,
        top: `${source.top}px`,
        width: `${source.width}px`,
        height: `${source.height}px`,
      });
      document.body.append(clone);
      row.style.visibility = "hidden";
      const animation = clone.animate(
        [
          { transform: "translate3d(0,0,0)", opacity: 0.96 },
          {
            transform: `translate3d(${target.left - source.left}px,${distance}px,0)`,
            opacity: 1,
          },
        ],
        { duration: 330, easing: "cubic-bezier(.16,1,.3,1)", fill: "forwards" },
      );
      flights.current.set(key, { animation, clone, row });
      animation.finished.then(() => stopFlight(key)).catch(() => {});
    }
  }, [selected]);

  const upload = async (event) => {
    const input = event.target,
      files = [...input.files];
    input.value = "";
    if (!files.length) return;
    setUploading(true);
    setError("");
    try {
      const uploaded = await onUpload(files);
      if (!alive.current) return;
      uploaded.forEach((file) => {
        const existing = library.find((item) => sameFile(item, file));
        add(
          existing
            ? { ...existing, ...file, id: existing.id || file.id }
            : file,
          uploadButton.current,
        );
      });
    } catch (error) {
      if (alive.current)
        setError(
          error?.message ||
            "Could not save the uploaded documents. Please try again.",
        );
    } finally {
      if (alive.current) setUploading(false);
    }
  };
  const switchTab = (next) => {
    [...flights.current.keys()].forEach(stopFlight);
    setTab(next);
  };
  const filtered = library.filter((file) =>
    file.name.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 50)),
    currentPage = Math.min(page, pages - 1);
  const visibleFiles = filtered.slice(currentPage * 50, (currentPage + 1) * 50);

  return (
    <section
      className="activity-documents"
      aria-labelledby="activity-materials-title"
    >
      <h3 id="activity-materials-title">Course materials</h3>
      <p>Select existing course documents, upload new ones, or combine both.</p>
      <div className="ad-tabs" role="tablist" aria-label="Document source">
        {[
          ["existing", "Existing Documents"],
          ["upload", "Upload New"],
        ].map(([id, label]) => (
          <button
            type="button"
            key={id}
            ref={(element) => {
              tabButtons.current[id] = element;
            }}
            role="tab"
            id={`ad-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`ad-panel-${id}`}
            tabIndex={tab === id ? 0 : -1}
            onClick={() => switchTab(id)}
            onKeyDown={(event) => {
              if (
                ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
              ) {
                event.preventDefault();
                const next =
                  event.key === "Home"
                    ? "existing"
                    : event.key === "End"
                      ? "upload"
                      : tab === "existing"
                        ? "upload"
                        : "existing";
                switchTab(next);
                tabButtons.current[next]?.focus();
              }
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="ad-panel-existing"
        aria-labelledby="ad-tab-existing"
        hidden={tab !== "existing"}
      >
        <label className="ad-search">
          <span>Search course documents</span>
          <input
            type="search"
            value={search}
            placeholder="Search by document name…"
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
          />
        </label>
        <div className="ad-document-count">
          {filtered.length} of {library.length} documents
        </div>
        <div
          className="ad-available-list"
          role="group"
          aria-label="Available documents"
        >
          {visibleFiles.map((file) => {
            const checked = selected.some((item) => sameFile(item, file));
            return (
              <label
                className={`ad-available-row ${checked ? "is-selected" : ""}`}
                key={documentKey(file)}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => {
                    if (event.target.checked)
                      add(
                        { ...file, source: "library" },
                        event.currentTarget.closest(".ad-available-row"),
                      );
                    else remove(file);
                  }}
                />
                <strong title={file.name}>{file.name}</strong>
                <span>{fileSize(file)}</span>
                <span className="sr-only">
                  {checked ? "Selected" : "Available"}
                </span>
              </label>
            );
          })}
          {!visibleFiles.length && (
            <p className="ad-empty">
              {search
                ? "No documents match your search."
                : "No existing documents yet. Use Upload New to add course materials."}
            </p>
          )}
        </div>
        {pages > 1 && (
          <div className="ad-pagination">
            <button
              type="button"
              className="secondary"
              disabled={!currentPage}
              onClick={() => setPage(currentPage - 1)}
            >
              Previous
            </button>
            <span>
              Page {currentPage + 1} of {pages}
            </span>
            <button
              type="button"
              className="secondary"
              disabled={currentPage === pages - 1}
              onClick={() => setPage(currentPage + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>
      <div
        role="tabpanel"
        id="ad-panel-upload"
        aria-labelledby="ad-tab-upload"
        hidden={tab !== "upload"}
      >
        <div className="ad-upload">
          <p>New uploads are also added to your course library.</p>
          <button
            ref={uploadButton}
            type="button"
            className="secondary"
            disabled={uploading}
            onClick={() => uploadInput.current?.click()}
          >
            {uploading ? "Saving documents…" : "Upload new documents"}
          </button>
          <input
            ref={uploadInput}
            hidden
            type="file"
            multiple
            accept=".pdf,.ppt,.pptx,.docx,.txt,.md"
            aria-label="Upload activity documents"
            onChange={upload}
          />
          <small>PDF, slides, Word, Markdown, or text.</small>
        </div>
      </div>
      {error && (
        <p role="alert" className="ad-error">
          {error}
        </p>
      )}
      <div className="ad-selected-heading">
        <h4>
          Selected Documents <span>{selected.length}</span>
        </h4>
        {selected.length > 0 && (
          <button
            type="button"
            className="secondary ad-clear-all"
            onClick={clearAll}
          >
            Clear all
          </button>
        )}
        <span
          className="sr-only"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {selected.length} document{selected.length === 1 ? "" : "s"} selected
        </span>
      </div>
      <div
        ref={stack}
        className="ad-selected-list"
        data-scrollable={selected.length > 4}
        aria-label="Selected documents"
        tabIndex={selected.length > 4 ? 0 : undefined}
      >
        {selected.map((file) => (
          <div
            className="ad-selected-row"
            key={documentKey(file)}
            ref={(element) => {
              const key = documentKey(file);
              if (element) rows.current.set(key, element);
              else rows.current.delete(key);
            }}
          >
            <svg
              aria-hidden="true"
              width="20"
              height="24"
              viewBox="0 0 24 28"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
            >
              <path d="M4 2h10l6 6v18H4zM14 2v6h6M8 14h8M8 19h6" />
            </svg>
            <div>
              <strong title={file.name}>{file.name}</strong>
              <small>{fileSize(file)}</small>
            </div>
            <button
              type="button"
              className="ad-remove"
              aria-label={`Remove ${file.name}`}
              onClick={() => remove(file)}
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>
        ))}
        {!selected.length && (
          <p className="ad-empty">Selected documents will appear here.</p>
        )}
      </div>
      <div className="ad-actions">
        <button
          type="button"
          disabled={!selected.length || uploading}
          onClick={onContinue}
        >
          Add Documents ({selected.length})
        </button>
        <small>Selections are saved with your activity draft.</small>
      </div>
    </section>
  );
}

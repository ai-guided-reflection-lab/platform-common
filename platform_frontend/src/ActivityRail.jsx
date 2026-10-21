import React, {
  Children,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

export default function CardRail({ children, label, className = "" }) {
  const track = useRef(null);
  const [edges, setEdges] = useState({ previous: false, next: false });
  const count = Children.count(children);
  const update = useCallback(() => {
    const node = track.current;
    if (!node) return;
    setEdges({
      previous: node.scrollLeft > 8,
      next: node.scrollWidth - node.clientWidth - node.scrollLeft > 8,
    });
  }, []);
  useEffect(() => {
    update();
    const observer =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    if (track.current) observer?.observe(track.current);
    window.addEventListener("resize", update);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [count, update]);
  const move = (direction) => {
    const node = track.current;
    const card = node?.firstElementChild;
    if (!card) return;
    const gap = parseFloat(getComputedStyle(node).columnGap) || 16;
    const reduced = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    node.scrollBy({
      left: direction * (card.getBoundingClientRect().width + gap),
      behavior: reduced ? "instant" : "smooth",
    });
  };
  return (
    <div
      className={`card-rail ${className} ${edges.previous ? "has-previous" : ""} ${edges.next ? "has-next" : ""}`}
    >
      <div
        className="card-rail-track"
        ref={track}
        role="list"
        aria-label={label}
        tabIndex={0}
        onScroll={update}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
            event.preventDefault();
            move(event.key === "ArrowRight" ? 1 : -1);
          }
        }}
      >
        {Children.map(children, (child) => (
          <div className="card-rail-item" role="listitem">
            {child}
          </div>
        ))}
      </div>
      {edges.previous && (
        <button
          type="button"
          className="card-rail-arrow previous"
          aria-label={`Previous ${label}`}
          onClick={() => move(-1)}
        >
          <Arrow previous />
        </button>
      )}
      {edges.next && (
        <button
          type="button"
          className="card-rail-arrow next"
          aria-label={`Next ${label}`}
          onClick={() => move(1)}
        >
          <Arrow />
        </button>
      )}
    </div>
  );
}
function Arrow({ previous = false }) {
  return (
    <svg
      width="23"
      height="23"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={previous ? { transform: "rotate(180deg)" } : undefined}
    >
      <path d="M4 12h15m-6-6 6 6-6 6" />
    </svg>
  );
}

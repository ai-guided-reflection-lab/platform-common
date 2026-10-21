export default function ToolIcon({ tool }) {
  if (tool === "debate") {
    return (
      <svg viewBox="0 0 32 32" aria-hidden="true">
        <path d="M4 6.5h15a4 4 0 0 1 4 4v5a4 4 0 0 1-4 4h-8l-5 4v-4H4a3 3 0 0 1-3-3v-7a3 3 0 0 1 3-3Z" />
        <path d="M24 12.5h3a4 4 0 0 1 4 4v5a4 4 0 0 1-4 4h-2v3l-4-3h-6a4 4 0 0 1-4-4" />
      </svg>
    );
  }
  if (tool === "socratic") {
    return (
      <svg viewBox="0 0 32 32" aria-hidden="true">
        <path d="M6 7.5h14a4 4 0 0 1 4 4v5a4 4 0 0 1-4 4h-7l-5 4v-4H6a4 4 0 0 1-4-4v-5a4 4 0 0 1 4-4Z" />
        <path d="M15 24.5h8l4 3v-3h1a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-1" />
      </svg>
    );
  }
  if (tool === "reflections") {
    return (
      <svg viewBox="0 0 32 32" aria-hidden="true">
        <path d="M8 3.5h13l5 5v20H8a3 3 0 0 1-3-3v-19a3 3 0 0 1 3-3Z" />
        <path d="M21 3.5v6h5M10 15h11M10 20h8M10 25h6" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 3.5 27 9.8v12.4L16 28.5 5 22.2V9.8Z" />
      <path d="m11 16 3 3 7-7M16 3.5v4M5 9.8l3.5 2M27 9.8l-3.5 2" />
    </svg>
  );
}

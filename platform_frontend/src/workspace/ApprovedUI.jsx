import React from "react";
const icons = {
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  book: "M12 5C8 2 4 3 2 4v16c4-1 7-1 10 1 3-2 6-2 10-1V4c-2-1-6-2-10 1Zm0 0v16",
  chat: "M4 4h16v12H9l-5 4V4Zm4 4h8M8 12h5",
  reflect: "M5 3h11l3 3v15H5V3Zm4 5h5M9 12h6M9 16h4",
  folder: "M3 7V4h6l2 3h10v13H3V7Z",
  chart: "M4 20V4M4 20h17M8 16v-5M13 16V7M18 16v-8",
  settings:
    "M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  check: "m5 12 4 4L19 6",
  plus: "M12 5v14M5 12h14",
  search: "M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  bell: "M6 16h12l-2-3V9a4 4 0 0 0-8 0v4l-2 3Zm4 4h4",
  calendar: "M4 5h16v16H4V5ZM8 2v6M16 2v6M4 10h16",
  upload: "M12 16V3M7 8l5-5 5 5M4 16v5h16v-5",
  users:
    "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 10v-3a7 7 0 0 1 14 0v3M17 4a4 4 0 0 1 0 7M20 14a5 5 0 0 1 2 4v3",
};
export function Icon({ name, size = 20 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={icons[name] || icons.book} />
    </svg>
  );
}
export function Pill({ value }) {
  return (
    <span className={`p-pill ${value}`}>
      {{
        in_progress: "In progress",
        not_started: "Not started",
        published: "Published",
        draft: "Draft",
        completed: "Completed",
        approved: "Enrolled",
        available: "Open to join",
        pending: "Request pending",
      }[value] || value}
    </span>
  );
}
export function PageHead({ eyebrow, title, description, children }) {
  return (
    <div className="p-page-heading">
      <div>
        <p className="p-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}

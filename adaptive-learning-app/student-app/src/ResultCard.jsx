import { useEffect, useRef, useState } from "react";

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function anonymousName(code, version = 0) {
  const colors = [
    "Silver",
    "Maple",
    "Coral",
    "Cedar",
    "Amber",
    "Willow",
    "Indigo",
    "River",
  ];
  const animals = [
    "Otter",
    "Owl",
    "Fox",
    "Panda",
    "Robin",
    "Falcon",
    "Dolphin",
    "Koala",
  ];
  const hash = Array.from(code).reduce(
    (n, c) => (n * 31 + c.charCodeAt(0)) >>> 0,
    version,
  );
  return `${colors[hash % colors.length]} ${animals[(hash >>> 4) % animals.length]}`;
}

export default function ResultCard({
  open,
  onClose,
  title,
  code,
  score,
  attempts = [],
}) {
  const dialog = useRef(null);
  const [version, setVersion] = useState(0);
  const [name, setName] = useState(() => anonymousName(code));
  const [error, setError] = useState("");
  const total = attempts.reduce((n, q) => n + q.attempts, 0);
  const displayName = name.trim() || anonymousName(code);
  useEffect(() => {
    const element = dialog.current;
    if (open && !element.open) element.showModal();
    else if (!open && element.open) element.close();
  }, [open]);
  const saveImage = () => {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 1000;
      const ctx = canvas.getContext("2d");
      ctx.font = "bold 32px sans-serif";
      const titleLines = [];
      let currentLine = "";
      for (const word of title.split(/\s+/)) {
        if (currentLine && ctx.measureText(currentLine + word).width > 875) {
          titleLines.push(currentLine);
          currentLine = "";
        }
        currentLine += word + " ";
      }
      titleLines.push(currentLine);
      canvas.height =
        720 +
        40 * (titleLines.length - 1) +
        Math.max(0, attempts.length - 5) * 32;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, 1000, canvas.height);
      ctx.fillStyle = "#2563eb";
      ctx.fillRect(0, 0, 1000, 14);
      ctx.fillStyle = "#516078";
      ctx.font = "22px sans-serif";
      ctx.fillText("SELF-DIRECTED LEARNING · COMPLETED", 60, 75);
      ctx.fillStyle = "#111827";
      ctx.font = "bold 32px sans-serif";
      let y = 135;
      titleLines.forEach((line, index) => {
        if (index) y += 40;
        ctx.fillText(line, 60, y, 875);
      });
      y += 65;
      ctx.font = "26px sans-serif";
      ctx.fillText(displayName, 60, y);
      y += 70;
      ctx.fillStyle = "#eff6ff";
      ctx.fillRect(60, y - 30, 880, 100);
      ctx.fillStyle = "#111827";
      ctx.font = "bold 28px sans-serif";
      ctx.fillText(`First-attempt score: ${score}/5`, 85, y + 10);
      ctx.font = "24px sans-serif";
      ctx.fillText(`Total quiz attempts: ${total}`, 85, y + 48);
      y += 125;
      ctx.fillStyle = "#516078";
      ctx.font = "22px sans-serif";
      for (const row of attempts) {
        ctx.fillText(
          `Question ${row.question_number}: ${row.attempts} ${row.attempts === 1 ? "attempt" : "attempts"}`,
          60,
          y,
        );
        y += 32;
      }
      y += 25;
      ctx.fillStyle = "#111827";
      ctx.font = "bold 22px sans-serif";
      ctx.fillText("Completion code", 60, y);
      y += 40;
      ctx.font = "22px monospace";
      ctx.fillText(code, 60, y);
      y += 55;
      ctx.fillStyle = "#516078";
      ctx.font = "22px sans-serif";
      ctx.fillText("Share this card with your TA.", 60, y);
      canvas.toBlob((blob) => {
        if (blob) downloadBlob(blob, `SDL-result-${code}.png`);
        else
          setError(
            "The image could not be created. You can screenshot the card instead.",
          );
      }, "image/png");
    } catch {
      setError(
        "The image could not be created. You can screenshot the card instead.",
      );
    }
  };
  return (
    <dialog
      ref={dialog}
      className="sdl-result-dialog"
      aria-label="Your result card"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="sdl-result-controls">
        <label>
          Anonymous display name
          <input
            maxLength={40}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            const next = version + 1;
            setVersion(next);
            setName(anonymousName(code, next));
          }}
        >
          Use another name
        </button>
      </div>
      <article className="sdl-result-card">
        <p className="eyebrow">Self-directed learning · Completed</p>
        <h2>{title}</h2>
        <h3>{displayName}</h3>
        <dl>
          <div>
            <dt>First-attempt quiz score</dt>
            <dd>{score}/5</dd>
          </div>
          <div>
            <dt>Total quiz attempts</dt>
            <dd>{total}</dd>
          </div>
        </dl>
        <ul>
          {attempts.map((row) => (
            <li key={row.question_number}>
              Question {row.question_number}
              <strong>
                {row.attempts} {row.attempts === 1 ? "attempt" : "attempts"}
              </strong>
            </li>
          ))}
        </ul>
        <strong>Completion code</strong>
        <code>{code}</code>
        <p>Share this card with your TA.</p>
      </article>
      <p className="help">
        Save the card as an image, or take a screenshot and share it with your
        TA. Your display name is only used on this card.
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="sdl-result-actions">
        <button type="button" onClick={saveImage}>
          Save card image
        </button>
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      </div>
    </dialog>
  );
}

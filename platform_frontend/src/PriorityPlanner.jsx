import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Notice } from "./ui";
import {
  AREAS,
  BALANCE_WINDOW,
  DAILY_TARGET,
  ENERGY_LEVELS,
  FOCUS_MODES,
  LIFE_CAREER_TARGET,
  TOP_LIMIT,
  emptyState,
  lifeCareerShare,
  loadState,
  rankTasks,
  saveState,
} from "./priorities";

const blankDraft = () => ({
  title: "",
  area: "life_career",
  impact: 3,
  effortMinutes: 30,
  energy: "steady",
  dueAt: "",
  notes: "",
});

const newId = () =>
  globalThis.crypto?.randomUUID?.() || `task-${Date.now()}-${Math.random()}`;

const percent = (value) => `${Math.round(value * 100)}%`;

function TaskForm({
  draft,
  setDraft,
  onSubmit,
  onCancel,
  submitLabel,
  idPrefix,
}) {
  const field = (name) => `${idPrefix}-${name}`;
  return (
    <form
      className="priority-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label htmlFor={field("title")}>
        Task
        <input
          id={field("title")}
          value={draft.title}
          required
          placeholder="e.g. Draft the internship application"
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
      </label>
      <div className="priority-form-row">
        <label htmlFor={field("area")}>
          Area
          <select
            id={field("area")}
            value={draft.area}
            onChange={(e) => setDraft({ ...draft, area: e.target.value })}
          >
            {Object.entries(AREAS).map(([id, area]) => (
              <option key={id} value={id}>
                {area.label}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor={field("impact")}>
          Impact (1–5)
          <input
            id={field("impact")}
            type="number"
            min="1"
            max="5"
            value={draft.impact}
            onChange={(e) =>
              setDraft({ ...draft, impact: Number(e.target.value) })
            }
          />
        </label>
        <label htmlFor={field("effort")}>
          Effort (minutes)
          <input
            id={field("effort")}
            type="number"
            min="5"
            step="5"
            value={draft.effortMinutes}
            onChange={(e) =>
              setDraft({ ...draft, effortMinutes: Number(e.target.value) })
            }
          />
        </label>
      </div>
      <div className="priority-form-row">
        <label htmlFor={field("energy")}>
          Energy needed
          <select
            id={field("energy")}
            value={draft.energy}
            onChange={(e) => setDraft({ ...draft, energy: e.target.value })}
          >
            {Object.entries(ENERGY_LEVELS).map(([id, level]) => (
              <option key={id} value={id}>
                {level.label}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor={field("due")}>
          Due (optional)
          <input
            id={field("due")}
            type="datetime-local"
            value={draft.dueAt}
            onChange={(e) => setDraft({ ...draft, dueAt: e.target.value })}
          />
        </label>
      </div>
      <label htmlFor={field("notes")}>
        Notes (optional)
        <textarea
          id={field("notes")}
          value={draft.notes}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
        />
      </label>
      <div className="priority-form-actions">
        <button type="submit">{submitLabel}</button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

export default function PriorityPlanner() {
  const [state, setState] = useState(() => emptyState());
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState(blankDraft);
  const [editing, setEditing] = useState(null);
  const [editDraft, setEditDraft] = useState(blankDraft);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setState(loadState());
    setReady(true);
  }, []);
  useEffect(() => {
    if (ready && !saveState(state))
      setError(
        "This browser blocked local storage, so today’s plan is not saved.",
      );
  }, [state, ready]);

  const { tasks, situation } = state;
  const ranked = useMemo(
    () => rankTasks(tasks, situation, now),
    [tasks, situation, now],
  );
  const open = tasks.filter((task) => !task.completedAt);
  const completed = tasks.filter((task) => task.completedAt);
  const share = lifeCareerShare(tasks);
  const plannedMinutes = ranked.reduce(
    (total, entry) => total + Number(entry.task.effortMinutes || 0),
    0,
  );

  const updateSituation = (patch) => {
    setState((prev) => ({
      ...prev,
      situation: { ...prev.situation, ...patch },
    }));
    setNow(Date.now());
  };
  const addTask = () => {
    if (!draft.title.trim()) return;
    setState((prev) => ({
      ...prev,
      tasks: [
        ...prev.tasks,
        {
          ...draft,
          id: newId(),
          title: draft.title.trim(),
          createdAt: new Date().toISOString(),
          completedAt: null,
        },
      ],
    }));
    setDraft(blankDraft());
    setError("");
  };
  const saveEdit = () => {
    setState((prev) => ({
      ...prev,
      tasks: prev.tasks.map((task) =>
        task.id === editing
          ? { ...task, ...editDraft, title: editDraft.title.trim() }
          : task,
      ),
    }));
    setEditing(null);
  };
  const toggleComplete = (id) =>
    setState((prev) => ({
      ...prev,
      tasks: prev.tasks.map((task) =>
        task.id === id
          ? {
              ...task,
              completedAt: task.completedAt ? null : new Date().toISOString(),
            }
          : task,
      ),
    }));
  const removeTask = (id) =>
    setState((prev) => ({
      ...prev,
      tasks: prev.tasks.filter((task) => task.id !== id),
    }));

  const countNote =
    open.length < DAILY_TARGET.min
      ? `Add ${DAILY_TARGET.min - open.length} more to reach a full day.`
      : open.length > DAILY_TARGET.max
        ? "More than eight open items — consider deferring a few."
        : "Good size for one day.";

  return (
    <>
      <Link className="back" to="/">
        ← All tools
      </Link>
      <div className="page-heading">
        <div>
          <p className="context">Personal workspace</p>
          <h1>Daily Priorities</h1>
          <p>
            Capture {DAILY_TARGET.min}–{DAILY_TARGET.max} things for today. The
            top {TOP_LIMIT} re-order themselves whenever your situation changes,
            and every position explains itself. Everything stays in this
            browser.
          </p>
        </div>
      </div>
      <Notice error={error} />

      <section className="section" aria-labelledby="situation-heading">
        <div className="panel">
          <h2 id="situation-heading">Today’s situation</h2>
          <p className="help">
            Change any of these and the ranking below recalculates immediately.
          </p>
          <div className="priority-form-row">
            <label htmlFor="situation-label">
              What kind of day is it?
              <input
                id="situation-label"
                value={situation.label}
                onChange={(e) => updateSituation({ label: e.target.value })}
              />
            </label>
            <label htmlFor="situation-minutes">
              Time available (minutes)
              <input
                id="situation-minutes"
                type="number"
                min="15"
                step="15"
                value={situation.minutesAvailable}
                onChange={(e) =>
                  updateSituation({ minutesAvailable: Number(e.target.value) })
                }
              />
            </label>
            <label htmlFor="situation-energy">
              Energy right now
              <select
                id="situation-energy"
                value={situation.energy}
                onChange={(e) => updateSituation({ energy: e.target.value })}
              >
                {Object.entries(ENERGY_LEVELS).map(([id, level]) => (
                  <option key={id} value={id}>
                    {level.label}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="situation-focus">
              Focus available
              <select
                id="situation-focus"
                value={situation.focus}
                onChange={(e) => updateSituation({ focus: e.target.value })}
              >
                {Object.entries(FOCUS_MODES).map(([id, mode]) => (
                  <option key={id} value={id}>
                    {mode.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="priority-stats">
            <div>
              <strong>{open.length}</strong>
              <small>open tasks · {countNote}</small>
            </div>
            <div>
              <strong>{plannedMinutes} min</strong>
              <small>
                planned in the top {ranked.length} vs{" "}
                {situation.minutesAvailable} min available
              </small>
            </div>
            <div>
              <strong>{share === null ? "—" : percent(share)}</strong>
              <small>
                life &amp; career share of your last {BALANCE_WINDOW}{" "}
                completions · target {percent(LIFE_CAREER_TARGET)}
              </small>
            </div>
          </div>
        </div>
      </section>

      <section className="section" aria-labelledby="ranking-heading">
        <div className="section-heading">
          <h2 id="ranking-heading">Top {TOP_LIMIT} right now</h2>
          <button className="quiet" onClick={() => setNow(Date.now())}>
            Re-rank
          </button>
        </div>
        {!ranked.length ? (
          <div className="empty">
            <h3>Nothing ranked yet</h3>
            <p>Add today’s tasks below and they will be sequenced for you.</p>
          </div>
        ) : (
          <ol className="priority-list" aria-labelledby="ranking-heading">
            {ranked.map(({ task, rank, score, reasons }) => (
              <li className="priority-row" key={task.id}>
                <span className="priority-rank" aria-hidden="true">
                  {rank}
                </span>
                <div className="priority-body">
                  <h3>
                    <span className="sr-only">Priority {rank}: </span>
                    {task.title}
                  </h3>
                  <p className="subtle">
                    {AREAS[task.area]?.label} · {task.effortMinutes} min ·{" "}
                    {ENERGY_LEVELS[task.energy]?.label} energy · impact{" "}
                    {task.impact}/5
                  </p>
                  <ul className="priority-reasons">
                    {reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
                <div className="priority-actions">
                  <span className="badge" title="Weighted priority score">
                    {score.toFixed(2)}
                  </span>
                  <button
                    className="secondary compact"
                    onClick={() => toggleComplete(task.id)}
                  >
                    Complete
                  </button>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="section" aria-labelledby="add-heading">
        <div className="panel">
          <h2 id="add-heading">Add a task</h2>
          <TaskForm
            idPrefix="add"
            draft={draft}
            setDraft={setDraft}
            onSubmit={addTask}
            submitLabel="Add task"
          />
        </div>
      </section>

      <section className="section" aria-labelledby="all-heading">
        <h2 id="all-heading">All tasks</h2>
        {!tasks.length ? (
          <div className="empty">
            <h3>No tasks captured yet</h3>
            <p>
              Your list lives only in this browser and is never sent to a
              server.
            </p>
          </div>
        ) : (
          <div className="assignment-list">
            {tasks.map((task) =>
              editing === task.id ? (
                <article className="assignment-row" key={task.id}>
                  <div className="priority-body">
                    <TaskForm
                      idPrefix={`edit-${task.id}`}
                      draft={editDraft}
                      setDraft={setEditDraft}
                      onSubmit={saveEdit}
                      onCancel={() => setEditing(null)}
                      submitLabel="Save task"
                    />
                  </div>
                </article>
              ) : (
                <article className="assignment-row" key={task.id}>
                  <div className="assignment-name">
                    <span className="subtle">
                      {AREAS[task.area]?.label} · {task.effortMinutes} min ·
                      impact {task.impact}/5
                    </span>
                    <h3>{task.title}</h3>
                    {task.notes && <span className="subtle">{task.notes}</span>}
                  </div>
                  <div className="assignment-state">
                    <span
                      className={`badge ${task.completedAt ? "completed" : ""}`}
                    >
                      {task.completedAt ? "Completed" : "Open"}
                    </span>
                  </div>
                  <div className="priority-actions">
                    <button
                      className="secondary compact"
                      onClick={() => toggleComplete(task.id)}
                    >
                      {task.completedAt ? "Reopen" : "Complete"}
                    </button>
                    <button
                      className="secondary compact"
                      onClick={() => {
                        setEditing(task.id);
                        setEditDraft({ ...blankDraft(), ...task });
                      }}
                    >
                      Edit
                    </button>
                    <button
                      className="quiet compact"
                      onClick={() => removeTask(task.id)}
                    >
                      Delete
                    </button>
                  </div>
                </article>
              ),
            )}
          </div>
        )}
        {completed.length > 0 && (
          <p className="help">
            {completed.length} completed · balance is measured from your most
            recent {BALANCE_WINDOW} completions.
          </p>
        )}
      </section>
    </>
  );
}

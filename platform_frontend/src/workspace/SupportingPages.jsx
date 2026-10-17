import React, { useState, useEffect } from "react";
import { api } from "../api";
import { useWorkspace } from "./WorkspaceContext";
import { Icon, Pill, PageHead } from "./ApprovedUI";
export function People() {
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const { items, user, refresh } = useWorkspace();
  const unique = new Map(
    items
      .flatMap((c) => c.students)
      .map((s) => [
        s.user_id || s.email,
        { ...s, id: s.user_id, name: s.name, role: "Student" },
      ]),
  );
  unique.set(user.user_id || user.id, {
    id: user.user_id || user.id,
    name: user.display_name || user.username,
    email: user.email,
    role: user.authority_level === 0 ? "Administrator" : "Professor",
  });
  const people = [...unique.values()];
  return (
    <>
      <PageHead
        eyebrow="PEOPLE & ACCESS"
        title="Your learning community."
        description="Review accounts and course access in one familiar place."
      />
      <section className="p-table-panel p-people-panel">
        <div className="p-table-toolbar">
          <h2>Workspace members</h2>
          <label className="p-search">
            <Icon name="search" />
            <input
              aria-label="Search people"
              placeholder="Search people…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
        {people
          .filter((p) => p.name.toLowerCase().includes(query.toLowerCase()))
          .map((p) => (
            <div className="p-person" key={p.id}>
              <span className="p-avatar">
                {p.name
                  .replace("Dr. ", "")
                  .split(" ")
                  .map((n) => n[0])
                  .join("")}
              </span>
              <div>
                <strong>{p.name}</strong>
                <small>{p.email}</small>
              </div>
              <select
                aria-label={`${p.name} role`}
                value={p.role}
                onChange={async (e) => {
                  try {
                    await api(`/admin/users/${p.id}/authority`, {
                      method: "POST",
                      body: {
                        authority_level: {
                          Student: 2,
                          Professor: 1,
                          Administrator: 0,
                        }[e.target.value],
                      },
                    });
                    setNotice("Account role updated.");
                    await refresh();
                  } catch (error) {
                    setNotice(error.message);
                  }
                }}
              >
                <option>Student</option>
                <option>Professor</option>
                <option>Administrator</option>
              </select>
              <Pill value="Active" />
            </div>
          ))}
      </section>
      {notice && (
        <p className="p-feedback" role="status">
          {notice}
        </p>
      )}
    </>
  );
}
export function Settings() {
  const { user } = useWorkspace();
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState(user.display_name || user.username);
  const [email, setEmail] = useState(user.email);

  return (
    <>
      <PageHead
        eyebrow="YOUR ACCOUNT"
        title="Make yourself at home."
        description="Manage your profile and learning preferences."
      />
      <section className="p-panel p-settings">
        <h2>Profile & preferences</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            try {
              await api("/platform/profile", {
                method: "PUT",
                body: { display_name: name, email },
              });
              setSaved(true);
            } catch (error) {
              setError(error.message);
              setSaved(false);
            }
          }}
        >
          <label>
            Display name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Email address
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Interface appearance
            <select defaultValue="light">
              <option value="light">University light</option>
            </select>
          </label>
          <label className="p-checkbox">
            <input
              type="checkbox"
              defaultChecked={
                localStorage.getItem(
                  `workspace-reminders:${user.user_id || user.id}`,
                ) !== "false"
              }
              onChange={(e) =>
                localStorage.setItem(
                  `workspace-reminders:${user.user_id || user.id}`,
                  String(e.target.checked),
                )
              }
            />{" "}
            Show learning reminders
          </label>
          <button>Save preferences</button>
          {error && (
            <p className="p-feedback" role="alert">
              {error}
            </p>
          )}
          {saved && (
            <p className="p-feedback" role="status">
              Preferences saved.
            </p>
          )}
        </form>
      </section>
    </>
  );
}
export function Insights() {
  const { items } = useWorkspace();
  const [details, setDetails] = useState([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("All students");
  useEffect(() => {
    let active = true;
    Promise.all(
      items.flatMap((c) =>
        c.activities
          .filter((a) => a.status === "published")
          .map((a) => api(`/platform/assignments/${a.id}`)),
      ),
    )
      .then((data) => {
        if (active) setDetails(data);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [items]);
  const records = details.flatMap((a) => a.students || []);
  const active = records.filter((s) => s.progress !== "not_started").length;
  const completed = records.filter((s) => s.progress === "completed").length;
  const stats = [
    [
      "Participation",
      records.length ? `${Math.round((active / records.length) * 100)}%` : "0%",
      "Students with an active attempt",
    ],
    [
      "Activities completed",
      String(completed),
      "Across your published activities",
    ],
    ["Needs support", "—", "Students to check in with"],
    ["Independent checks", "—", "Evidence of understanding"],
  ];
  const grouped = new Map();
  for (const s of records) {
    const id = s.student_id;
    const row = grouped.get(id) || {
      name: s.display_name || s.username,
      total: 0,
      done: 0,
    };
    row.total++;
    if (s.progress === "completed") row.done++;
    grouped.set(id, row);
  }
  const students = [...grouped.values()].map((s) => [
    s.name,
    Math.round((s.done / s.total) * 100),
    s.done === s.total ? "Completed" : s.done ? "In progress" : "Not started",
  ]);
  const concepts = [];
  return (
    <>
      <PageHead
        eyebrow="LEARNING INSIGHTS"
        title="See the learning behind the numbers."
        description="A shared view of understanding, participation, and where a little support can help."
      />
      {error && (
        <p className="p-feedback" role="alert">
          {error}
        </p>
      )}
      <div className="p-stat-grid">
        {stats.map(([label, value, note]) => (
          <div className="p-stat" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{note}</small>
          </div>
        ))}
      </div>
      <section className="p-panel">
        <div className="p-section-title">
          <div>
            <h2>Understanding by concept</h2>
            <p>Evidence from practice and independent checks</p>
          </div>
          <span className="p-label">{items.length} courses</span>
        </div>
        <div className="p-bars">
          {concepts.map(([name, percent]) => (
            <div key={name}>
              <div>
                <span>{name}</span>
                <strong>{percent}%</strong>
              </div>
              <div className="p-bar-track">
                <span style={{ width: `${percent}%` }} />
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="p-table-panel">
        <div className="p-table-toolbar">
          <h2>Student progress</h2>
          <select
            aria-label="Filter student progress"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option>All students</option>
            <option>Needs support</option>
          </select>
        </div>
        {students
          .filter(
            (s) => selected === "All students" || s[2] === "Needs support",
          )
          .map(([name, percent, status]) => (
            <div className="p-person" key={name}>
              <span className="p-avatar">
                {name
                  .split(" ")
                  .map((n) => n[0])
                  .join("")}
              </span>
              <div>
                <strong>{name}</strong>
                <small>Published course activities</small>
              </div>
              <span className="p-progress-count">{percent}%</span>
              <Pill value={status} />
            </div>
          ))}
      </section>
    </>
  );
}

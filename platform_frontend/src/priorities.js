export const STORAGE_KEY = "cluball_priority_planner_v1";
export const TOP_LIMIT = 10;
export const DAILY_TARGET = { min: 5, max: 8 };
export const LIFE_CAREER_TARGET = 0.8;
export const BALANCE_WINDOW = 20;

export const AREAS = {
  life_career: { label: "Life & career", short: "Career" },
  exploration: { label: "Exploration", short: "Explore" },
};
export const ENERGY_LEVELS = {
  low: { label: "Low", rank: 1 },
  steady: { label: "Steady", rank: 2 },
  high: { label: "High", rank: 3 },
};
export const FOCUS_MODES = {
  light: { label: "Light — short, shallow blocks" },
  mixed: { label: "Mixed — a normal day" },
  deep: { label: "Deep — protected focus time" },
};
export const WEIGHTS = {
  urgency: 0.3,
  impact: 0.28,
  fit: 0.18,
  readiness: 0.14,
  balance: 0.1,
};

export const DEFAULT_SITUATION = {
  label: "Regular day",
  minutesAvailable: 180,
  energy: "steady",
  focus: "mixed",
};

export const emptyState = () => ({
  tasks: [],
  situation: { ...DEFAULT_SITUATION },
});

const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const round = (value) => Math.round(value * 1000) / 1000;

export function daysUntilDue(dueAt, now = Date.now()) {
  if (!dueAt) return null;
  const due = new Date(dueAt).getTime();
  if (Number.isNaN(due)) return null;
  return (due - now) / 86400000;
}

export function urgencyScore(task, now = Date.now()) {
  const days = daysUntilDue(task.dueAt, now);
  if (days === null) return 0.35;
  if (days <= 0) return 1;
  if (days <= 1) return 0.92;
  return clamp(0.92 - (days - 1) / 14, 0.1, 0.92);
}

export function impactScore(task) {
  return clamp((Number(task.impact) - 1) / 4);
}

export function fitScore(task, situation) {
  const available = Number(situation.minutesAvailable);
  const effort = Math.max(5, Number(task.effortMinutes) || 0);
  if (!available || available <= 0) return 0.2;
  const ratio = effort / available;
  if (ratio <= 1) return clamp(1 - ratio * 0.2, 0.8, 1);
  return clamp(1 / (ratio * ratio), 0.05, 0.8);
}

export function readinessScore(task, situation) {
  const required = ENERGY_LEVELS[task.energy]?.rank ?? 2;
  const current = ENERGY_LEVELS[situation.energy]?.rank ?? 2;
  let score = current >= required ? 1 : 1 - 0.3 * (required - current);
  if (situation.focus === "deep") score += required === 3 ? 0.12 : -0.06;
  if (situation.focus === "light") score += required === 1 ? 0.12 : -0.1;
  return clamp(score, 0.05, 1);
}

export function lifeCareerShare(tasks) {
  const done = tasks
    .filter((task) => task.completedAt)
    .sort((a, b) => new Date(b.completedAt) - new Date(a.completedAt))
    .slice(0, BALANCE_WINDOW);
  if (!done.length) return null;
  return (
    done.filter((task) => task.area === "life_career").length / done.length
  );
}

export function balanceScore(task, share) {
  const current = share === null ? LIFE_CAREER_TARGET : share;
  const gap = LIFE_CAREER_TARGET - current;
  const lean = clamp(0.5 + gap * 1.5, 0, 1);
  return task.area === "life_career" ? lean : 1 - lean;
}

function reasonsFor(task, factors, situation, now) {
  const reasons = [];
  const days = daysUntilDue(task.dueAt, now);
  if (days !== null && days <= 0) reasons.push("Overdue — clear it first");
  else if (days !== null && days <= 1) reasons.push("Due within a day");
  else if (days !== null && days <= 3)
    reasons.push(`Due in ${Math.ceil(days)} days`);
  else if (days === null) reasons.push("No deadline set");
  if (factors.impact >= 0.75) reasons.push("High impact on what matters");
  else if (factors.impact <= 0.25) reasons.push("Low stated impact");
  if (factors.fit >= 0.8)
    reasons.push(`Fits your ${situation.minutesAvailable} min window`);
  else
    reasons.push(`Needs ${task.effortMinutes} min — longer than today allows`);
  if (factors.readiness >= 0.9)
    reasons.push(
      `Matches ${ENERGY_LEVELS[situation.energy]?.label.toLowerCase()} energy`,
    );
  else if (factors.readiness <= 0.6)
    reasons.push("Demands more energy than you have");
  if (factors.balance >= 0.65)
    reasons.push(
      task.area === "life_career"
        ? "Pulls you back toward the 80% life & career target"
        : "Exploration is under its 20% share",
    );
  return reasons;
}

export function rankTasks(tasks, situation, now = Date.now()) {
  const share = lifeCareerShare(tasks);
  return tasks
    .filter((task) => !task.completedAt)
    .map((task) => {
      const factors = {
        urgency: urgencyScore(task, now),
        impact: impactScore(task),
        fit: fitScore(task, situation),
        readiness: readinessScore(task, situation),
        balance: balanceScore(task, share),
      };
      const score = Object.entries(WEIGHTS).reduce(
        (total, [key, weight]) => total + factors[key] * weight,
        0,
      );
      return {
        task,
        score: round(score),
        factors,
        reasons: reasonsFor(task, factors, situation, now),
      };
    })
    .sort(
      (a, b) =>
        b.score - a.score ||
        new Date(a.task.createdAt || 0) - new Date(b.task.createdAt || 0),
    )
    .slice(0, TOP_LIMIT)
    .map((entry, index) => ({ ...entry, rank: index + 1 }));
}

export function loadState(storage = globalThis.localStorage) {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    if (!raw) return emptyState();
    const parsed = JSON.parse(raw);
    return {
      tasks: Array.isArray(parsed.tasks) ? parsed.tasks : [],
      situation: { ...DEFAULT_SITUATION, ...(parsed.situation || {}) },
    };
  } catch {
    return emptyState();
  }
}

export function saveState(state, storage = globalThis.localStorage) {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(state));
    return true;
  } catch {
    return false;
  }
}

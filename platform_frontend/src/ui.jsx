import { label } from "./api";
export function Notice({ error, children }) {
  return error ? (
    <div className="notice error" role="alert">
      {error}
    </div>
  ) : children ? (
    <div className="notice" role="status">
      {children}
    </div>
  ) : null;
}
export function Badge({ value }) {
  return <span className={`badge ${value}`}>{label(value)}</span>;
}

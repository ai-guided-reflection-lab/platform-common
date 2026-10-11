export default function DebateConfig({ value, onChange }) {
  const change = (key, next) => onChange({ ...value, [key]: next });
  return (
    <div className="form-columns">
      <div>
        <label>
          Debate scenario or topic
          <textarea
            rows={8}
            required
            minLength={10}
            maxLength={10000}
            value={value.scenario}
            onChange={(event) => change("scenario", event.target.value)}
            placeholder="Should a city use facial recognition in public transit? Explain the decision context and constraints students should consider."
          />
        </label>
        <p className="help">
          Give students enough context to take a position and defend it.
        </p>
      </div>
      <div>
        <label>
          Opening prompt
          <textarea
            rows={4}
            maxLength={2000}
            value={value.opening_prompt}
            onChange={(event) => change("opening_prompt", event.target.value)}
            placeholder="Take a position and give your strongest reason."
          />
        </label>
        <label>
          Messages required before completion
          <input
            type="number"
            min={1}
            max={100}
            value={value.minimum_messages}
            onChange={(event) =>
              change("minimum_messages", Number(event.target.value))
            }
          />
        </label>
        <p className="help">
          Students can mark the assignment complete after this many responses.
        </p>
      </div>
    </div>
  );
}

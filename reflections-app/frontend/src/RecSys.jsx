import { useState } from 'react';

const API = '/api';

function FileUploadField({ label, hint, accept, onChange }) {
    const [fileName, setFileName] = useState('');
    return (
        <div className="form-group">
            <label>{label}</label>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>
                {hint}
            </div>
            <label
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.6rem 0.85rem',
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                    cursor: 'pointer',
                    fontSize: '0.875rem',
                }}
            >
                <span className="btn btn-outline" style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                    Choose file
                </span>
                <span style={{ color: fileName ? 'var(--text)' : 'var(--text-muted)' }}>
                    {fileName || 'No file selected'}
                </span>
                <input
                    type="file"
                    accept={accept}
                    style={{ display: 'none' }}
                    onChange={(e) => {
                        const f = e.target.files[0];
                        if (f) { setFileName(f.name); onChange(f); }
                    }}
                />
            </label>
        </div>
    );
}

function SimilarTable({ similar }) {
    return (
        <div style={{ overflowX: 'auto', marginTop: '0.75rem' }}>
            <table>
                <thead>
                    <tr>
                        <th style={{ width: 60 }}>#</th>
                        <th style={{ width: 80 }}>Score</th>
                        <th>Challenge</th>
                        <th>Solution</th>
                        <th>Student</th>
                    </tr>
                </thead>
                <tbody>
                    {similar.map((s, i) => (
                        <tr key={i}>
                            <td style={{ color: 'var(--text-muted)' }}>{i + 1}</td>
                            <td>
                                <span
                                    className={`score ${s.cos_score >= 0.7 ? 'high' : s.cos_score >= 0.4 ? 'mid' : 'low'}`}
                                >
                                    {s.cos_score.toFixed(3)}
                                </span>
                            </td>
                            <td style={{ maxWidth: 260, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                                {s.challenge}
                            </td>
                            <td style={{ maxWidth: 260, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                                {s.solution}
                            </td>
                            <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{s.name}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function StudentCard({ result, index, isLLM }) {
    const [open, setOpen] = useState(false);

    return (
        <div className="card" style={{ marginBottom: '1rem' }}>
            <div
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    cursor: 'pointer',
                    gap: '1rem',
                }}
                onClick={() => setOpen((v) => !v)}
            >
                <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600 }}>
                        {index + 1}. {result.name || '(unnamed)'}
                        {result.email && (
                            <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: '0.5rem', fontSize: '0.85rem' }}>
                                {result.email}
                            </span>
                        )}
                    </div>
                    <div
                        style={{
                            color: 'var(--text-muted)',
                            fontSize: '0.85rem',
                            marginTop: '0.25rem',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            display: '-webkit-box',
                            WebkitLineClamp: open ? 'unset' : 2,
                            WebkitBoxOrient: 'vertical',
                        }}
                    >
                        {result.reflection}
                    </div>
                </div>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', flexShrink: 0 }}>
                    {open ? '▲ collapse' : '▼ expand'}
                </span>
            </div>

            {open && (
                <div style={{ marginTop: '1rem', borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                        Top {result.similar.length} Similar Historical Students
                    </div>
                    <SimilarTable similar={result.similar} />

                    {isLLM && result.llm_output && (
                        <div style={{ marginTop: '1.25rem' }}>
                            <div style={{ fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--accent)', marginBottom: '0.5rem' }}>
                                Generated Recommendation Email
                            </div>
                            <div
                                style={{
                                    background: 'var(--surface-2)',
                                    border: '1px solid var(--border)',
                                    borderRadius: 'var(--radius)',
                                    padding: '1rem',
                                    fontSize: '0.875rem',
                                    lineHeight: 1.7,
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                }}
                            >
                                {result.llm_output}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default function RecSys({ mode }) {
    const isLLM = mode === 'llm-scs';
    const title = isLLM ? 'LLM-SCS' : 'SCS';
    const subtitle = isLLM
        ? 'Similarity-based matching + LLM-generated recommendation email'
        : 'Similarity-based matching — find top-k similar historical student reflections';

    const [historicalFile, setHistoricalFile] = useState(null);
    const [currentFile, setCurrentFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState('');

    const canRun = historicalFile && currentFile && !loading;

    const handleRun = async () => {
        setLoading(true);
        setError('');
        setResults(null);

        const formData = new FormData();
        formData.append('mode', mode);
        formData.append('historical_data', historicalFile);
        formData.append('current_students', currentFile);

        try {
            const resp = await fetch(`${API}/rec-sys/run`, { method: 'POST', body: formData });
            const data = await resp.json();
            if (!resp.ok) {
                setError(data.detail || 'Request failed');
            } else {
                setResults(data.results);
            }
        } catch (e) {
            setError(`Network error: ${e.message}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="page" style={{ maxWidth: 960 }}>
            <h1>{title}</h1>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
                {subtitle}
            </p>

            {/* CSV format instructions */}
            <div
                className="card"
                style={{ marginBottom: '1.5rem', borderColor: 'var(--primary)', background: 'var(--surface)' }}
            >
                <div style={{ fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                    Required CSV Format
                </div>
                <div className="row" style={{ gap: '2rem' }}>
                    <div>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>Historical Data</div>
                        <code style={{ fontSize: '0.78rem', color: 'var(--accent)', whiteSpace: 'pre' }}>
                            {'name, challenge, solution'}
                        </code>
                    </div>
                    <div>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>Current Students</div>
                        <code style={{ fontSize: '0.78rem', color: 'var(--accent)', whiteSpace: 'pre' }}>
                            {"Full Name, Email Address, student's reflection"}
                        </code>
                    </div>
                </div>
            </div>

            {/* File uploads */}
            <div className="row" style={{ alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                    <FileUploadField
                        label="Historical Data (training)"
                        hint="CSV with past student challenges and solutions"
                        accept=".csv"
                        onChange={setHistoricalFile}
                    />
                </div>
                <div style={{ flex: 1 }}>
                    <FileUploadField
                        label="Current Students"
                        hint="CSV with students whose reflections need recommendations"
                        accept=".csv"
                        onChange={setCurrentFile}
                    />
                </div>
            </div>

            <div style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
                <button className="btn btn-primary" onClick={handleRun} disabled={!canRun}>
                    {loading ? 'Running…' : `Run ${title}`}
                </button>
                {loading && (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                        Computing embeddings{isLLM ? ' and generating emails' : ''}…
                    </span>
                )}
            </div>

            {error && (
                <div
                    style={{
                        background: 'rgba(248,113,113,0.1)',
                        border: '1px solid var(--danger)',
                        borderRadius: 'var(--radius)',
                        padding: '0.75rem 1rem',
                        color: 'var(--danger)',
                        marginBottom: '1.5rem',
                        fontSize: '0.875rem',
                    }}
                >
                    {error}
                </div>
            )}

            {results !== null && (
                <div>
                    <div
                        style={{
                            fontSize: '0.8rem',
                            fontWeight: 600,
                            textTransform: 'uppercase',
                            letterSpacing: '0.05em',
                            color: 'var(--text-muted)',
                            marginBottom: '1rem',
                        }}
                    >
                        Results — {results.length} student{results.length !== 1 ? 's' : ''}
                    </div>
                    {results.length === 0 ? (
                        <div className="empty">No results returned.</div>
                    ) : (
                        results.map((r, i) => (
                            <StudentCard key={i} result={r} index={i} isLLM={isLLM} />
                        ))
                    )}
                </div>
            )}
        </div>
    );
}

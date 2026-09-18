import { useState, useEffect } from 'react';

const API = '/api';

function scoreCls(v, max = 1) {
    const pct = v / max;
    if (pct >= 0.7) return 'score high';
    if (pct >= 0.4) return 'score mid';
    return 'score low';
}

export default function Dashboard() {
    const [modules, setModules] = useState([]);
    const [moduleId, setModuleId] = useState('');
    const [rows, setRows] = useState([]);
    const [subTopics, setSubTopics] = useState([]);

    useEffect(() => {
        fetch(`${API}/modules`).then((r) => r.json()).then(setModules).catch(() => { });
    }, []);

    useEffect(() => {
        if (!moduleId) { setRows([]); setSubTopics([]); return; }
        Promise.all([
            fetch(`${API}/analytics/${moduleId}`).then((r) => r.json()).catch(() => []),
            fetch(`${API}/modules/${moduleId}/config`).then((r) => r.ok ? r.json() : null).catch(() => null),
        ]).then(([analyticsData, cfg]) => {
            setRows(analyticsData || []);
            setSubTopics((cfg && cfg.sub_topics) || []);
        });
    }, [moduleId]);

    // Compute sub-topic heatmap: count sessions where each sub-topic was missing or had a misconception.
    // Misconceptions are free-text from LLM, so match by checking if any significant word from the
    // topic name appears in the misconception string (rather than the full topic string).
    const heatmapData = subTopics.map((topic) => {
        const topicWords = topic.toLowerCase().split(/\W+/).filter((w) => w.length > 2);
        return {
            topic,
            count: rows.filter((r) =>
                r.missing_topics?.includes(topic) ||
                r.misconceptions?.some((m) => {
                    const mLower = m.toLowerCase();
                    return topicWords.some((word) => mLower.includes(word));
                })
            ).length,
        };
    }).sort((a, b) => b.count - a.count);

    const maxMissing = Math.max(...heatmapData.map((d) => d.count), 1);

    return (
        <div className="page">
            <h1>Analytics Dashboard</h1>

            <div className="form-group" style={{ maxWidth: 360 }}>
                <label>Module</label>
                <select value={moduleId} onChange={(e) => setModuleId(e.target.value)}>
                    <option value="">Select module…</option>
                    {modules.map((m) => (
                        <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                </select>
            </div>

            {moduleId && rows.length === 0 && (
                <p className="empty">No analytics data yet for this module.</p>
            )}

            {rows.length > 0 && (
                <>
                    <div className="card" style={{ overflowX: 'auto' }}>
                        <table>
                            <thead>
                                <tr>
                                    <th>Student</th>
                                    <th>Depth</th>
                                    <th>Confidence</th>
                                    <th>Engagement</th>
                                    <th>Missing Topics</th>
                                    <th>Misconceptions</th>
                                    <th>Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <tr key={r.conversation_id}>
                                        <td>{r.student_anonymized_id}</td>
                                        <td><span className={scoreCls(r.reflection_depth_score)}>{r.reflection_depth_score.toFixed(1)}/1</span></td>
                                        <td><span className={scoreCls(r.confidence_level, 5)}>{r.confidence_level}/5</span></td>
                                        <td><span className={scoreCls(r.engagement_score)}>{r.engagement_score.toFixed(1)}/1</span></td>
                                        <td>{r.missing_topics.length ? r.missing_topics.map((t) => <span key={t} className="tag">{t}</span>) : '—'}</td>
                                        <td>{r.misconceptions.length ? r.misconceptions.map((t, i) => <span key={i} className="tag">{t}</span>) : '—'}</td>
                                        <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{new Date(r.created_at).toLocaleDateString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Simple bar chart — reflection depth per student */}
                    <div className="card">
                        <h3 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                            Reflection Depth by Student
                        </h3>
                        <div className="bar-chart">
                            {rows.map((r) => (
                                <div key={r.conversation_id} className="bar-col">
                                    <div className="bar" style={{ height: `${r.reflection_depth_score * 100}px` }} />
                                    <span className="bar-label">{r.student_anonymized_id}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Sub-topic heatmap */}
                    {subTopics.length > 0 && (
                        <div className="card">
                            <h3 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                                Sub-topic Misconception Frequency
                            </h3>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                                {heatmapData.map(({ topic, count }) => (
                                    <div key={topic} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                        <span style={{ minWidth: 200, fontSize: '0.85rem' }}>{topic}</span>
                                        <div style={{ flex: 1, background: 'var(--border, #e5e7eb)', borderRadius: 4, height: 14 }}>
                                            <div style={{
                                                width: `${(count / maxMissing) * 100}%`,
                                                height: '100%',
                                                background: count === 0 ? 'var(--border, #e5e7eb)' : 'var(--danger, #ef4444)',
                                                borderRadius: 4,
                                                transition: 'width 0.3s',
                                            }} />
                                        </div>
                                        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', minWidth: 24, textAlign: 'right' }}>
                                            {count}
                                        </span>
                                    </div>
                                ))}
                            </div>
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                                Number of sessions where each sub-topic was flagged as missing or had a related misconception.
                            </p>
                        </div>
                    )}

                    {/* Per-session subtopic coverage grid */}
                    {subTopics.length > 0 && (
                        <div className="card" style={{ overflowX: 'auto' }}>
                            <h3 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                                Per-session Sub-topic Coverage
                            </h3>
                            <table>
                                <thead>
                                    <tr>
                                        <th>Student</th>
                                        <th>Date</th>
                                        {subTopics.map((t) => (
                                            <th key={t} style={{ fontSize: '0.75rem', fontWeight: 500, maxWidth: 100, wordBreak: 'break-word' }}>{t}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.map((r) => (
                                        <tr key={r.conversation_id}>
                                            <td>{r.student_anonymized_id}</td>
                                            <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                                {new Date(r.created_at).toLocaleDateString()}
                                            </td>
                                            {subTopics.map((t) => {
                                                const missing = r.missing_topics?.includes(t);
                                                return (
                                                    <td key={t} style={{ textAlign: 'center', fontSize: '1rem' }}>
                                                        {missing ? (
                                                            <span style={{ color: 'var(--danger, #ef4444)' }}>✗</span>
                                                        ) : (
                                                            <span style={{ color: 'var(--success, #22c55e)' }}>✓</span>
                                                        )}
                                                    </td>
                                                );
                                            })}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

import { useState, useEffect, useRef } from 'react';

const API = '/api';

// ── Milestone results display ──────────────────────────────────────────────
function MilestoneResults({ similar, onReset, assigned }) {
    return (
        <div className="page">
            <h1>Your Reflection — Similar Experiences</h1>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
                Here are the most similar challenges and solutions from previous students.
            </p>
            {similar.length === 0 ? (
                <div className="empty">No similar responses found.</div>
            ) : (
                similar.map((s, i) => (
                    <div className="card" key={i} style={{ marginBottom: '1rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                            <span style={{ fontWeight: 600 }}>#{i + 1} — {s.name}</span>
                            <span className={`score ${s.cos_score >= 0.7 ? 'high' : s.cos_score >= 0.4 ? 'mid' : 'low'}`}>
                                {s.cos_score.toFixed(3)} similarity
                            </span>
                        </div>
                        <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                            <span style={{ color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', fontSize: '0.75rem', letterSpacing: '0.04em' }}>Challenge</span>
                            <p style={{ margin: '0.25rem 0 0', lineHeight: 1.6 }}>{s.challenge}</p>
                        </div>
                        <div style={{ fontSize: '0.85rem' }}>
                            <span style={{ color: 'var(--accent)', fontWeight: 600, textTransform: 'uppercase', fontSize: '0.75rem', letterSpacing: '0.04em' }}>Solution</span>
                            <p style={{ margin: '0.25rem 0 0', lineHeight: 1.6 }}>{s.solution}</p>
                        </div>
                    </div>
                ))
            )}
            <button className="btn btn-outline" onClick={onReset} style={{ marginTop: '0.5rem' }}>
                {assigned ? 'Back to assignment' : 'New Reflection'}
            </button>
        </div>
    );
}

// ── Main Chat component ────────────────────────────────────────────────────
export default function Chat({ assignmentSession = null }) {
    const [phase, setPhase] = useState('setup'); // setup | chatting | ended | milestone | milestone_results
    const [modules, setModules] = useState([]);
    const [moduleId, setModuleId] = useState('');
    const [moduleType, setModuleType] = useState('topic_based');
    const [milestonePrompt, setMilestonePrompt] = useState('');
    const [studentId, setStudentId] = useState('student-1');

    // Topic-based chat state
    const [sessionId, setSessionId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [seconds, setSeconds] = useState(600);
    const [evaluation, setEvaluation] = useState(null);
    const [questionIndex, setQuestionIndex] = useState(0);
    const [totalQuestions, setTotalQuestions] = useState(0);
    const [isBonusPhase, setIsBonusPhase] = useState(false);
    const [paused, setPaused] = useState(false);

    // Milestone state
    const [milestoneReflection, setMilestoneReflection] = useState('');
    const [milestoneResults, setMilestoneResults] = useState([]);
    const [milestoneLoading, setMilestoneLoading] = useState(false);
    const [milestoneError, setMilestoneError] = useState('');

    const bottomRef = useRef(null);
    const pending = useRef(null);
    const [chatError, setChatError] = useState('');

    // The platform owns identity, configuration, persistence, and completion.
    useEffect(() => {
        if (!assignmentSession) return;
        const { attempt, config } = assignmentSession;
        const state = attempt.engine_state || {};
        const milestone = config.module_type === 'milestone_based';
        setSessionId(attempt.id);
        setModuleType(config.module_type);
        setMilestonePrompt(config.milestone_prompt || '');
        setMessages(attempt.messages || []);
        setQuestionIndex(state.question_index || 0);
        setTotalQuestions(state.total_questions || 0);
        setIsBonusPhase(!!state.is_bonus_phase);
        setEvaluation(attempt.result?.evaluation || null);
        setMilestoneResults(attempt.result?.similar || []);
        setPhase(attempt.status === 'completed'
            ? (milestone ? 'milestone_results' : 'ended')
            : (milestone ? 'milestone' : 'chatting'));
    }, [assignmentSession?.attempt, assignmentSession?.config]);

    async function sendAssigned(text) {
        if (!pending.current || pending.current.message !== text) {
            pending.current = { message: text, request_id: crypto.randomUUID() };
        }
        await assignmentSession.send(pending.current);
        pending.current = null;
    }

    useEffect(() => {
        if (assignmentSession) return;
        fetch(`${API}/modules`).then((r) => r.json()).then(setModules).catch(() => { });
    }, []);

    // When module changes, look up its type and config
    useEffect(() => {
        if (assignmentSession) return;
        if (!moduleId) { setModuleType('topic_based'); setMilestonePrompt(''); return; }
        const mod = modules.find((m) => m.id === moduleId);
        const type = mod?.module_type || 'topic_based';
        setModuleType(type);
        if (type === 'milestone_based') {
            fetch(`${API}/modules/${moduleId}/config`)
                .then((r) => r.ok ? r.json() : null)
                .then((cfg) => setMilestonePrompt(cfg?.milestone_prompt || ''))
                .catch(() => setMilestonePrompt(''));
        }
    }, [moduleId, modules]);

    // Timer (topic-based only)
    useEffect(() => {
        if (phase !== 'chatting' || paused || loading) return;
        if (seconds <= 0) { handleEnd(); return; }
        const id = setInterval(() => setSeconds((s) => s - 1), 1000);
        return () => clearInterval(id);
    }, [phase, seconds, paused, loading]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const fmt = (s) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

    // ── Topic-based start ──────────────────────────────────────────
    const handleStart = async () => {
        if (!moduleId) return;
        setLoading(true);
        try {
            const res = await fetch(`${API}/chat/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ student_id: studentId, module_id: moduleId }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed');
            setSessionId(data.session_id);
            setMessages([{ role: 'assistant', content: data.greeting }]);
            setTotalQuestions(data.total_questions || 0);
            setQuestionIndex(0);
            setIsBonusPhase(false);
            setPhase('chatting');
        } catch (e) {
            alert(e.message);
        } finally {
            setLoading(false);
        }
    };

    // ── Milestone submit ───────────────────────────────────────────
    const handleMilestoneSubmit = async () => {
        if (!milestoneReflection.trim()) return;
        setMilestoneLoading(true);
        setMilestoneError('');
        try {
            if (assignmentSession) {
                await sendAssigned(milestoneReflection.trim());
                return;
            }
            const res = await fetch(`${API}/rec-sys/milestone`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    module_id: moduleId,
                    student_name: studentId,
                    student_email: '',
                    reflection: milestoneReflection.trim(),
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Request failed');
            setMilestoneResults(data.similar || []);
            setPhase('milestone_results');
        } catch (e) {
            setMilestoneError(e.message);
        } finally {
            setMilestoneLoading(false);
        }
    };

    const handleSend = async () => {
        if (!input.trim() || loading) return;
        const userMsg = input.trim();
        if (assignmentSession) {
            setLoading(true);
            setChatError('');
            try {
                await sendAssigned(userMsg);
                setInput('');
            } catch (e) {
                setChatError(e.message);
            } finally {
                setLoading(false);
            }
            return;
        }
        setInput('');
        setMessages((prev) => [...prev, { role: 'user', content: userMsg }]);
        setLoading(true);
        try {
            const res = await fetch(`${API}/chat/message`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, message: userMsg, time_remaining: seconds }),
            });
            const data = await res.json();
            setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);
            if (data.total_questions > 0) {
                setQuestionIndex(data.question_index);
                setTotalQuestions(data.total_questions);
                setIsBonusPhase(data.is_bonus_phase);
            }
        } catch {
            setMessages((prev) => [...prev, { role: 'assistant', content: '⚠ Error reaching server.' }]);
        } finally {
            setLoading(false);
        }
    };

    const handleEnd = async () => {
        if (!sessionId || loading) return;
        if (assignmentSession) {
            setLoading(true);
            setChatError('');
            try {
                await assignmentSession.complete();
            } catch (e) {
                setChatError(e.message);
                setPaused(true); // A failed timer completion must not loop requests.
            } finally {
                setLoading(false);
            }
            return;
        }
        setPhase('ended');
        try {
            const res = await fetch(`${API}/chat/end`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId }),
            });
            const data = await res.json();
            setEvaluation(data.evaluation);
        } catch { /* silent */ }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
    };

    const resetAll = () => {
        if (assignmentSession) { assignmentSession.back(); return; }
        setPhase('setup');
        setMessages([]);
        setSeconds(600);
        setEvaluation(null);
        setQuestionIndex(0);
        setTotalQuestions(0);
        setIsBonusPhase(false);
        setPaused(false);
        setMilestoneReflection('');
        setMilestoneResults([]);
        setMilestoneError('');
    };

    // ── Milestone results screen ───────────────────────────────────
    if (phase === 'milestone_results') {
        return <MilestoneResults similar={milestoneResults} onReset={resetAll} assigned={!!assignmentSession} />;
    }

    // ── Setup screen ───────────────────────────────────────────────
    if (phase === 'setup') {
        return (
            <div className="setup-screen">
                <h2>Start a Reflection Session</h2>
                <div className="form-group">
                    <label>Student ID</label>
                    <input type="text" value={studentId} onChange={(e) => setStudentId(e.target.value)} />
                </div>
                <div className="form-group">
                    <label>Module</label>
                    <select value={moduleId} onChange={(e) => setModuleId(e.target.value)}>
                        <option value="">Select a module…</option>
                        {modules.map((m) => (
                            <option key={m.id} value={m.id}>
                                {m.name} ({m.module_type === 'milestone_based' ? 'Milestone' : 'Topic'})
                            </option>
                        ))}
                    </select>
                </div>
                <button
                    className="btn btn-primary"
                    onClick={() => moduleType === 'milestone_based' ? setPhase('milestone') : handleStart()}
                    disabled={!moduleId || loading}
                >
                    {loading ? 'Starting…' : 'Begin Session'}
                </button>
            </div>
        );
    }

    // ── Milestone reflection screen ────────────────────────────────
    if (phase === 'milestone') {
        return (
            <div className="page" style={{ maxWidth: 680 }}>
                <h1>Reflection</h1>
                {milestonePrompt && (
                    <div className="card" style={{ marginBottom: '1.5rem', borderColor: 'var(--primary)' }}>
                        <p style={{ fontSize: '1rem', lineHeight: 1.7 }}>{milestonePrompt}</p>
                    </div>
                )}
                <div className="form-group">
                    <label>Your Reflection</label>
                    <textarea
                        aria-label="Your Reflection"
                        disabled={milestoneLoading}
                        rows={7}
                        placeholder="Describe your challenge and any solutions you've tried…"
                        value={milestoneReflection}
                        onChange={(e) => setMilestoneReflection(e.target.value)}
                        style={{ width: '100%', resize: 'vertical' }}
                    />
                </div>
                {milestoneError && (
                    <div style={{
                        background: 'rgba(248,113,113,0.1)', border: '1px solid var(--danger)',
                        borderRadius: 'var(--radius)', padding: '0.75rem 1rem',
                        color: 'var(--danger)', marginBottom: '1rem', fontSize: '0.875rem',
                    }}>
                        {milestoneError}
                    </div>
                )}
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                    <button
                        className="btn btn-primary"
                        onClick={handleMilestoneSubmit}
                        disabled={!milestoneReflection.trim() || milestoneLoading}
                    >
                        {milestoneLoading ? 'Finding similar experiences…' : 'Submit Reflection'}
                    </button>
                    <button className="btn btn-outline" onClick={resetAll}>Back</button>
                </div>
            </div>
        );
    }

    // ── Ended screen ───────────────────────────────────────────────
    if (phase === 'ended') {
        return (
            <div className="page">
                <h1>Session Complete</h1>
                {evaluation ? (
                    <div className="card">
                        <p><strong>Depth Score:</strong> {evaluation.reflection_depth_score}</p>
                        <p><strong>Confidence:</strong> {evaluation.confidence_level}/5</p>
                        <p><strong>Engagement:</strong> {evaluation.engagement_score}</p>
                        <p><strong>Topics Covered:</strong> {evaluation.topics_covered?.join(', ') || 'n/a'}</p>
                        <p><strong>Missing Topics:</strong> {evaluation.missing_topics?.join(', ') || 'none'}</p>
                        <p><strong>Misconceptions:</strong> {evaluation.misconceptions?.join(', ') || 'none'}</p>
                    </div>
                ) : (
                    <p className="empty">{assignmentSession ? 'Your reflection has been saved.' : 'Evaluating transcript…'}</p>
                )}
                {assignmentSession && <div className="card" aria-label="Saved transcript">
                    {messages.map((m, i) => <p key={i}><strong>{m.role === 'user' ? 'You' : 'Reflections'}:</strong> {m.content}</p>)}
                </div>}
                <button className="btn btn-outline" onClick={resetAll}>{assignmentSession ? 'Back to assignment' : 'New Session'}</button>
            </div>
        );
    }

    // ── Chat screen (topic-based) ──────────────────────────────────
    return (
        <div className="chat-container" style={assignmentSession ? { flex: 1, minHeight: 0, width: '100%' } : undefined}>
            <div className="chat-header">
                <span style={{ fontWeight: 600 }}>Reflection Session</span>
                {totalQuestions > 0 && (
                    isBonusPhase
                        ? <span style={{ fontSize: '0.75rem', padding: '0.15rem 0.5rem', borderRadius: '999px', background: 'var(--accent)', color: '#fff', fontWeight: 500 }}>Bonus Questions</span>
                        : <span style={{ fontSize: '0.8rem', fontVariantNumeric: 'tabular-nums', color: 'var(--text-muted)' }}>{questionIndex + 1}/{totalQuestions}</span>
                )}
                <span className={`timer ${seconds <= 60 && !paused ? 'warning' : ''}`}>{fmt(seconds)}</span>
                {seconds <= 60 && (
                    <button className="btn btn-outline" style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }} onClick={() => setPaused((p) => !p)}>
                        {paused ? 'Resume' : 'Pause'}
                    </button>
                )}
                <button className="btn btn-danger" onClick={handleEnd} disabled={loading || (totalQuestions > 0 && !isBonusPhase)}>
                    End Session
                </button>
            </div>

            {chatError && <p role="alert" style={{ color: 'var(--danger)' }}>{chatError}</p>}
            <div className="messages">
                {messages.map((m, i) => (
                    <div key={i} className={`message ${m.role}`}>
                        {m.content.split('\n\n').map((para, j) => (
                            <p key={j} style={{ margin: j === 0 ? 0 : '0.6rem 0 0' }}>{para}</p>
                        ))}
                    </div>
                ))}
                {loading && <div className="message assistant" style={{ opacity: 0.5 }}>Thinking…</div>}
                <div ref={bottomRef} />
            </div>

            <div className="chat-input">
                <input
                    type="text"
                    aria-label="Your message"
                    placeholder="Type your reflection…"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={loading}
                />
                <button className="btn btn-primary" onClick={handleSend} disabled={loading || !input.trim()}>
                    Send
                </button>
            </div>
        </div>
    );
}

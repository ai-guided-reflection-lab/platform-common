import { useState, useEffect } from 'react';

const API = '/api';

export default function ProfessorConfig() {
    const [modules, setModules] = useState([]);
    const [selectedModule, setSelectedModule] = useState('');
    const [selectedModuleType, setSelectedModuleType] = useState('topic_based');
    const [newModuleName, setNewModuleName] = useState('');
    const [newModuleType, setNewModuleType] = useState('topic_based');

    // Topic-based config fields
    const [topics, setTopics] = useState([]);
    const [topicInput, setTopicInput] = useState('');
    const [subTopics, setSubTopics] = useState([]);
    const [subTopicInput, setSubTopicInput] = useState('');
    const [depth, setDepth] = useState('surface');
    const [style, setStyle] = useState('supportive');
    const [mustApp, setMustApp] = useState(false);
    const [customNotes, setCustomNotes] = useState('');

    // Milestone-based config fields
    const [milestonePrompt, setMilestonePrompt] = useState('');
    const [historicalFile, setHistoricalFile] = useState(null);
    const [historicalFileName, setHistoricalFileName] = useState('');
    const [hasHistoricalData, setHasHistoricalData] = useState(false);
    const [uploadingHistorical, setUploadingHistorical] = useState(false);

    const [saving, setSaving] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [status, setStatus] = useState('');

    useEffect(() => {
        fetchModules();
    }, []);

    const fetchModules = () => {
        fetch(`${API}/modules`).then((r) => r.json()).then(setModules).catch(() => { });
    };

    // Load existing config when module changes
    useEffect(() => {
        if (!selectedModule) { setSelectedModuleType('topic_based'); return; }

        // Get module type from the modules list
        const mod = modules.find((m) => m.id === selectedModule);
        const modType = mod?.module_type || 'topic_based';
        setSelectedModuleType(modType);

        fetch(`${API}/modules/${selectedModule}/config`)
            .then((r) => { if (!r.ok) throw new Error('none'); return r.json(); })
            .then((cfg) => {
                setTopics(cfg.required_topics || []);
                setSubTopics(cfg.sub_topics || []);
                setDepth(cfg.expected_depth || 'surface');
                setStyle(cfg.probing_style || 'supportive');
                setMustApp(cfg.must_include_application || false);
                setCustomNotes(cfg.custom_notes || '');
                setMilestonePrompt(cfg.milestone_prompt || '');
                setHasHistoricalData(cfg.has_historical_data || false);
            })
            .catch(() => {
                setTopics([]);
                setSubTopics([]);
                setDepth('surface');
                setStyle('supportive');
                setMustApp(false);
                setCustomNotes('');
                setMilestonePrompt('');
                setHasHistoricalData(false);
            });
    }, [selectedModule, modules]);

    const handleCreateModule = async () => {
        if (!newModuleName.trim()) return;
        const res = await fetch(`${API}/modules`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newModuleName.trim(), module_type: newModuleType }),
        });
        const mod = await res.json();
        setModules((prev) => [...prev, mod]);
        setSelectedModule(mod.id);
        setNewModuleName('');
    };

    const addTopic = () => {
        const t = topicInput.trim();
        if (t && !topics.includes(t)) { setTopics((prev) => [...prev, t]); setTopicInput(''); }
    };
    const removeTopic = (t) => setTopics((prev) => prev.filter((x) => x !== t));
    const handleTopicKeyDown = (e) => { if (e.key === 'Enter') { e.preventDefault(); addTopic(); } };

    const addSubTopic = () => {
        const t = subTopicInput.trim();
        if (t && !subTopics.includes(t)) { setSubTopics((prev) => [...prev, t]); setSubTopicInput(''); }
    };
    const removeSubTopic = (t) => setSubTopics((prev) => prev.filter((x) => x !== t));
    const handleSubTopicKeyDown = (e) => { if (e.key === 'Enter') { e.preventDefault(); addSubTopic(); } };

    const handleAutoGenerate = async () => {
        if (!topics.length) return;
        setGenerating(true);
        setStatus('');
        try {
            const res = await fetch(`${API}/modules/subtopics/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ main_topics: topics }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Generation failed');
            setSubTopics(data.sub_topics || []);
            setStatus('Sub-topics generated');
        } catch (e) {
            setStatus('✗ ' + e.message);
        } finally {
            setGenerating(false);
        }
    };

    const handleUploadHistorical = async () => {
        if (!historicalFile || !selectedModule) return;
        setUploadingHistorical(true);
        setStatus('');
        const formData = new FormData();
        formData.append('file', historicalFile);
        try {
            const res = await fetch(`${API}/modules/${selectedModule}/config/historical`, {
                method: 'POST',
                body: formData,
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Upload failed');
            setHasHistoricalData(true);
            setStatus(`✓ Historical data uploaded (${data.rows} rows)`);
        } catch (e) {
            setStatus('✗ ' + e.message);
        } finally {
            setUploadingHistorical(false);
        }
    };

    const handleSave = async () => {
        if (!selectedModule) return;
        setSaving(true);
        setStatus('');
        const payload = {
            required_topics: topics,
            sub_topics: subTopics,
            expected_depth: depth,
            probing_style: style,
            must_include_application: mustApp,
            custom_notes: customNotes,
            milestone_prompt: milestonePrompt,
        };
        try {
            const res = await fetch(`${API}/modules/${selectedModule}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => null);
            if (!res.ok) throw new Error((data && data.detail) || 'Save failed');
            if (data) {
                setTopics(data.required_topics || []);
                setSubTopics(data.sub_topics || []);
                setDepth(data.expected_depth || depth);
                setStyle(data.probing_style || style);
                setMustApp(Boolean(data.must_include_application));
                setCustomNotes(data.custom_notes || '');
                setMilestonePrompt(data.milestone_prompt || '');
                setHasHistoricalData(data.has_historical_data || false);
            }
            setStatus('✓ Saved');
        } catch (e) {
            setStatus('✗ ' + e.message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="page">
            <h1>Professor Module Configuration</h1>

            {/* Create new module */}
            <div className="card">
                <div className="form-group">
                    <label>Create New Module</label>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                            type="text"
                            placeholder="e.g. Week 3 — Neural Networks"
                            value={newModuleName}
                            onChange={(e) => setNewModuleName(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleCreateModule(); }}
                        />
                        <select
                            value={newModuleType}
                            onChange={(e) => setNewModuleType(e.target.value)}
                            style={{ width: 'auto', flexShrink: 0 }}
                        >
                            <option value="topic_based">Topic Based</option>
                            <option value="milestone_based">Milestone Based</option>
                        </select>
                        <button className="btn btn-outline" onClick={handleCreateModule}>Create</button>
                    </div>
                    <small style={{ color: 'var(--text-muted)', fontSize: '0.78rem', marginTop: '0.35rem', display: 'block' }}>
                        <strong>Topic Based</strong> — guided LLM chat covering configured topics.&nbsp;
                        <strong>Milestone Based</strong> — single open reflection matched against historical student responses.
                    </small>
                </div>
            </div>

            {/* Select module */}
            <div className="card">
                <div className="form-group">
                    <label>Select Module</label>
                    <select value={selectedModule} onChange={(e) => setSelectedModule(e.target.value)}>
                        <option value="">Choose…</option>
                        {modules.map((m) => (
                            <option key={m.id} value={m.id}>
                                {m.name} ({m.module_type === 'milestone_based' ? 'Milestone' : 'Topic'})
                            </option>
                        ))}
                    </select>
                </div>

                {selectedModule && selectedModuleType === 'topic_based' && (
                    <>
                        <div className="form-group">
                            <label>Main Topics</label>
                            <div className="tag-input-wrapper">
                                {topics.map((t) => (
                                    <span key={t} className="tag">
                                        {t}
                                        <span className="remove" onClick={() => removeTopic(t)}>×</span>
                                    </span>
                                ))}
                                <input
                                    type="text"
                                    placeholder="Add topic + Enter"
                                    value={topicInput}
                                    onChange={(e) => setTopicInput(e.target.value)}
                                    onKeyDown={handleTopicKeyDown}
                                />
                            </div>
                        </div>

                        <div className="form-group">
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                                <label style={{ marginBottom: 0 }}>Sub Topics</label>
                                <button
                                    className="btn btn-outline"
                                    style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
                                    onClick={handleAutoGenerate}
                                    disabled={!topics.length || generating}
                                >
                                    {generating ? 'Generating…' : 'Auto-generate'}
                                </button>
                            </div>
                            <div className="tag-input-wrapper">
                                {subTopics.map((t) => (
                                    <span key={t} className="tag">
                                        {t}
                                        <span className="remove" onClick={() => removeSubTopic(t)}>×</span>
                                    </span>
                                ))}
                                <input
                                    type="text"
                                    placeholder="Add sub-topic + Enter"
                                    value={subTopicInput}
                                    onChange={(e) => setSubTopicInput(e.target.value)}
                                    onKeyDown={handleSubTopicKeyDown}
                                />
                            </div>
                            <small style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                                Chat questions will follow these sub-topics in order.
                            </small>
                        </div>

                        <div className="row">
                            <div className="form-group" style={{ flex: 1 }}>
                                <label>Expected Depth</label>
                                <select value={depth} onChange={(e) => setDepth(e.target.value)}>
                                    <option value="surface">Surface</option>
                                    <option value="applied">Applied</option>
                                    <option value="analytical">Analytical</option>
                                </select>
                            </div>
                            <div className="form-group" style={{ flex: 1 }}>
                                <label>Probing Style</label>
                                <select value={style} onChange={(e) => setStyle(e.target.value)}>
                                    <option value="supportive">Supportive</option>
                                    <option value="socratic">Socratic</option>
                                </select>
                            </div>
                        </div>

                        <div className="form-group">
                            <div className="checkbox-row">
                                <input
                                    type="checkbox"
                                    id="mustApp"
                                    checked={mustApp}
                                    onChange={(e) => setMustApp(e.target.checked)}
                                />
                                <label htmlFor="mustApp" style={{ textTransform: 'none', fontSize: '0.9rem', marginBottom: 0 }}>
                                    Must include application-based question
                                </label>
                            </div>
                        </div>

                        <div className="form-group">
                            <label>Custom Notes for LLM</label>
                            <textarea
                                rows={4}
                                placeholder="e.g. Focus on the student's understanding of backpropagation before moving to other topics."
                                value={customNotes}
                                onChange={(e) => setCustomNotes(e.target.value)}
                                style={{ width: '100%', resize: 'vertical' }}
                            />
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                                {saving ? 'Saving…' : 'Save Configuration'}
                            </button>
                            {status && <span style={{ fontSize: '0.85rem' }}>{status}</span>}
                        </div>
                    </>
                )}

                {selectedModule && selectedModuleType === 'milestone_based' && (
                    <>
                        <div className="form-group">
                            <label>Reflection Prompt</label>
                            <textarea
                                rows={3}
                                placeholder="e.g. What was your biggest challenge this week, and what solution did you try?"
                                value={milestonePrompt}
                                onChange={(e) => setMilestonePrompt(e.target.value)}
                                style={{ width: '100%', resize: 'vertical' }}
                            />
                            <small style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                                This question is shown to students in the chat screen.
                            </small>
                        </div>

                        <div className="form-group">
                            <label>Historical Student Data (CSV)</label>
                            <small style={{ color: 'var(--text-muted)', fontSize: '0.78rem', display: 'block', marginBottom: '0.4rem' }}>
                                Required columns: <code style={{ color: 'var(--accent)' }}>name, challenge, solution</code>
                            </small>
                            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                <label style={{
                                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                                    padding: '0.5rem 0.85rem', background: 'var(--surface-2)',
                                    border: '1px solid var(--border)', borderRadius: 'var(--radius)',
                                    cursor: 'pointer', fontSize: '0.875rem', flex: 1,
                                }}>
                                    <span className="btn btn-outline" style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}>
                                        Choose file
                                    </span>
                                    <span style={{ color: historicalFileName ? 'var(--text)' : 'var(--text-muted)' }}>
                                        {historicalFileName || 'No file selected'}
                                    </span>
                                    <input
                                        type="file"
                                        accept=".csv"
                                        style={{ display: 'none' }}
                                        onChange={(e) => {
                                            const f = e.target.files[0];
                                            if (f) { setHistoricalFile(f); setHistoricalFileName(f.name); }
                                        }}
                                    />
                                </label>
                                <button
                                    className="btn btn-outline"
                                    onClick={handleUploadHistorical}
                                    disabled={!historicalFile || uploadingHistorical}
                                >
                                    {uploadingHistorical ? 'Uploading…' : 'Upload'}
                                </button>
                            </div>
                            {hasHistoricalData && (
                                <div style={{ marginTop: '0.4rem', fontSize: '0.8rem', color: 'var(--success)' }}>
                                    ✓ Historical data is uploaded
                                </div>
                            )}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                                {saving ? 'Saving…' : 'Save Configuration'}
                            </button>
                            {status && <span style={{ fontSize: '0.85rem' }}>{status}</span>}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

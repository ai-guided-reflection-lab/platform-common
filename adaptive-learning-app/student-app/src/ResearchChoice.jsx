import {useState} from 'react';
import {api} from './api';

export default function ResearchChoice({assignmentId, notice, choice, onSaved}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  if (!notice) return null;
  async function save(value) {
    if (saving) return;
    setSaving(true);
    setError('');
    try {
      const result = await api(`/student/assignments/${assignmentId}/research-choice`, {
        method:'POST', body:JSON.stringify({choice:value,notice_version:notice.version}),
      });
      if (result?.choice !== value || result?.notice_version !== notice.version)
        throw new Error('Your choice was not confirmed. Please try again.');
      onSaved(result);
    } catch (e) {
      setError(e.message || 'Your choice could not be saved. Your result card is still available.');
    } finally {
      setSaving(false);
    }
  }
  return <section className="sdl-research-choice" aria-label="Optional research participation">
    <h3>{notice.title}</h3>
    <p>Your response has been submitted.</p>
    <p>{notice.text}</p>
    <p>{notice.optional}</p>
    <div className="learning-choices">
      <button className="secondary" type="button" disabled={saving || choice?.choice === 'yes'} aria-pressed={choice?.choice === 'yes'} onClick={()=>save('yes')}>Yes, happy to help!</button>
      <button className="secondary" type="button" disabled={saving || choice?.choice === 'no'} aria-pressed={choice?.choice === 'no'} onClick={()=>save('no')}>No thanks, not this time</button>
    </div>
    {saving && <p role="status">Saving your choice…</p>}
    {!saving && choice && <p role="status">Your research-use choice is saved: {choice.choice === 'yes' ? 'Yes' : 'No'}. You can change it using the buttons above.</p>}
    {error && <p role="alert">{error}</p>}
    <p className="help">Your choice will appear on your result card. You can view the card without answering.</p>
  </section>;
}

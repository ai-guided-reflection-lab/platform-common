"""Assignment integration of local-socratic-chat, using isolated PostgreSQL fixtures."""
import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.classifier import _classification_from_observation as observation
from app.answer_evaluation import AnswerEvaluation
from app.schemas import Source, CompletionSummary, ClarificationOption
from platform_app import engines, store
from platform_tests.test_assignments import draft, publish

SOURCE = Source(document_id='doc', chunk_id='doc:0', title='Code review',
                text='A reviewer checks correctness, consistency and comprehension before a change is submitted.', score=1)


def evaluation(score=85, critical=False):
    return AnswerEvaluation(concept='comprehension', keyword_coverage=.8, semantic_alignment=.8,
        rubric_score=.8, total_score=score, correctness=3, completeness=3, reasoning=3, application=None,
        supported_concepts=('consistency',), missing_concepts=('correctness',), critical_misconception=critical,
        misconception='Review does not guarantee defect-free code.' if critical else None,
        feedback='You explained consistency; also consider correctness.', confidence=.9)


def setup_pipeline(monkeypatch, score=85, critical=False, role='student_answer'):
    calls = []
    async def classify(message, history, learning_topic=None):
        calls.append(('classify', learning_topic, [m.content for m in history]))
        return observation(message_role=role, concepts=('comprehension',), rewritten_query='comprehension')
    async def assess(*args, **kwargs):
        calls.append(('evaluate', kwargs.get('concept_hint')))
        return evaluation(score, critical) if args[3].assessment_candidate else None
    async def generate(message, history, sources, **kwargs):
        calls.append(('generate', kwargs))
        return 'Sam can read Alex’s change. How would Sam check that it also works correctly?'
    async def summary(original, latest, history, sources, assessment, reflection):
        calls.append(('summary', original, reflection))
        return CompletionSummary(original_question=original, student_reflection=reflection,
            demonstrated=[latest], final_comment='You connected review to team understanding.',
            misconception_correction=None, scenario_wrap_up='Sam checks Alex’s patch before it joins the project.',
            opening_answer='Code review checks a proposed change with another engineer.')
    monkeypatch.setattr(engines, 'classify_message', classify)
    monkeypatch.setattr(engines, 'evaluate_student_answer', assess)
    monkeypatch.setattr(engines.rag, 'generate_answer', generate)
    monkeypatch.setattr(engines.rag, 'generate_completion_summary', summary)
    monkeypatch.setattr(engines.rag, 'retrieve_snapshot', lambda *args, **kw: [SOURCE])
    return calls


def sample():
    return ({'id':uuid4(), 'tool':'socratic', 'snapshot':{'config':{}, 'chunks':[]}},
            {'id':uuid4(), 'messages':[{'role':'assistant','content':'Alex asks Sam to review a patch. Why?'}],
             'engine_state':{'socratic':{'learning_topic':'What is code review?', 'stable_concept':'code review'}}})


def test_stable_topic_and_feedback_survive_different_retrieval_targets(monkeypatch):
    calls=setup_pipeline(monkeypatch, score=49, critical=True)
    assignment, attempt=sample()
    result=asyncio.run(engines._socratic_message(assignment, attempt, 'Review guarantees no bugs.'))
    assert result['assessment']['concept']=='code review'
    assert result['socratic']['stable_concept']=='code review'
    assert calls[0][1]=='What is code review?'
    generated=next(c[1] for c in calls if c[0]=='generate')
    assert generated['stable_concept']=='code review'
    assert generated['evaluation'].critical_misconception
    assert generated['evaluation'].feedback.startswith('You explained')
    assert result['socratic']['phase']=='teaching'


def test_high_score_with_critical_misconception_does_not_complete(monkeypatch):
    setup_pipeline(monkeypatch, score=90, critical=True)
    assignment, attempt=sample()
    result=asyncio.run(engines._socratic_message(assignment, attempt, 'All bugs must be gone.'))
    assert result['socratic']['phase']=='teaching'


def test_support_is_not_assessed_as_mastery(monkeypatch):
    calls=setup_pipeline(monkeypatch, role='support_request')
    assignment, attempt=sample()
    result=asyncio.run(engines._socratic_message(assignment, attempt, 'Please explain more clearly.'))
    assert 'assessment' not in result
    assert result['socratic']['phase']=='teaching'
    assert next(c[1] for c in calls if c[0]=='generate')['classification'].message_role=='support_request'


def test_clarification_choice_is_server_bound_and_not_scored(monkeypatch):
    calls=setup_pipeline(monkeypatch)
    assignment, attempt=sample()
    attempt['engine_state']['socratic']['pending_clarification']={'original_question':'Any update?', 'options':[
        {'label':'Explain again', 'message_role':'support_request', 'resolved_message':'Explain the previous review question again.'}]}
    result=asyncio.run(engines._socratic_message(assignment, attempt, 'Explain again', 0))
    assert not any(c[0]=='evaluate' for c in calls)
    assert result['socratic']['classification']['message_role']=='support_request'
    assert 'pending_clarification' not in result['socratic']
    with pytest.raises(HTTPException) as exc:
        asyncio.run(engines._socratic_message(assignment, attempt, 'Fake', 2))
    assert exc.value.status_code==422


def test_learning_checkpoint_reflection_submission_and_persisted_scores(client, roster, monkeypatch):
    calls=setup_pipeline(monkeypatch)
    item,_=draft(client,roster,config={'prompt':'What is code review?'})
    publish(client,roster,item,monkeypatch)
    path=f"/api/platform/assignments/{item['id']}"; h=roster['headers']['student']
    started=client.post(path+'/start',headers=h)
    assert started.status_code==200
    assert client.post(path+'/reflection',headers=h,json={'summary':'Too soon','request_id':str(uuid4())}).status_code==409
    rid=str(uuid4()); body={'message':'Review helps teammates understand a change before it is submitted.','request_id':rid}
    result=client.post(path+'/messages',headers=h,json=body)
    assert result.status_code==200,result.text
    state=result.json()['engine_state']['socratic']
    assert state['phase']=='awaiting_reflection'
    assert not any(c[0]=='generate' for c in calls)
    retry=client.post(path+'/messages',headers=h,json=body).json()
    assert retry['messages']==result.json()['messages']
    assert retry['engine_state']==result.json()['engine_state']
    with store.connection() as conn:
        rows=conn.execute('SELECT concept,total_score,evaluation FROM assignment_assessments_platform WHERE attempt_id=%s', (result.json()['id'],)).fetchall()
    assert len(rows)==1 and rows[0]['total_score']==85
    assert rows[0]['evaluation']['feedback'].startswith('You explained')
    assert client.post(path+'/complete',headers=h).status_code==422
    assert client.post(path+'/messages',headers=h,json={**body,'request_id':str(uuid4())}).status_code==409
    summary={'summary':'Another engineer checks my change for correctness and whether the team can understand it.', 'request_id':str(uuid4())}
    async def failed(*args): raise RuntimeError('temporary model failure')
    with monkeypatch.context() as failure:
        failure.setattr(engines.rag,'generate_completion_summary',failed)
        assert client.post(path+'/reflection',headers=h,json=summary).status_code==503
    assert client.get(path+'/attempt',headers=h).json()['engine_state']['socratic']['phase']=='awaiting_reflection'
    final=client.post(path+'/reflection',headers=h,json=summary)
    assert final.status_code==200,final.text
    assert final.json()['engine_state']['socratic']['phase']=='ready_to_submit'
    assert final.json()['engine_state']['socratic']['completion_summary']['student_reflection']==summary['summary']
    retry=client.post(path+'/reflection',headers=h,json=summary).json()
    assert retry['messages']==final.json()['messages']
    assert retry['engine_state']==final.json()['engine_state']
    assert len([c for c in calls if c[0]=='summary'])==1
    assert client.post(path+'/complete',headers=h).json()['status']=='completed'
    assert client.get(path+'/attempt',headers=h).json()['result']['student_reflection']==summary['summary']

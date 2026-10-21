import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import db, objective_extraction
from platform_app import engines, store
from platform_tests.test_assignments import draft


def material(roster, text='A reviewer checks correctness and consistency before a change enters the codebase.'):
    fid=db.save_rag_file('review.txt','text/plain',text.encode(),course_id=roster['course'],user_id=roster['prof'])
    did=f'doc-{uuid4()}'
    db.replace_document_chunks(fid,did,'review.txt',[{'text':text}],[[.1]*1536],'text-embedding-3-small',course_id=roster['course'])
    chunk=db.get_document_chunks_for_objectives(fid)[0]['chunk_id']
    return fid,did,chunk


def candidate(chunk):
    return dict(keywords=['code review','correctness'],objective='Explain why another engineer checks a proposed change.',
        prerequisites=['A shared codebase'],success_criteria=['Connects review to correctness'],
        common_misconceptions=['Review is only formatting'],
        diagnostic_question='What should a reviewer check, and why?',source_chunk_ids=[chunk],confidence=.9,evidence_type='explicit')


def fake_model(monkeypatch, chunk):
    requests=[]
    async def completion(key,base,request):
        requests.append(request)
        payload={'objectives':[candidate(chunk),{**candidate('invented-chunk'), 'keywords':['Unsupported idea']}]}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    monkeypatch.setattr(objective_extraction,'chat_completion',completion)
    monkeypatch.setattr(objective_extraction.settings,'llm_client_config',lambda purpose:('Groq','test','http://example.invalid','model'))
    return requests


def test_generate_review_edit_and_preserve_reviewed_objectives(client,roster,monkeypatch):
    fid,did,chunk=material(roster);requests=fake_model(monkeypatch,chunk)
    base=f"/api/courses/{roster['course']}";h=roster['headers']['prof']
    generated=client.post(base+f'/documents/{fid}/learning-objectives/generate',headers=h)
    assert generated.status_code==202,generated.text
    status=client.get(base+f'/documents/{fid}/learning-objectives/generation-status',headers=h)
    assert status.json()['status']=='completed' and status.json()['objectives_drafted']==1
    rows=client.get(base+'/learning-objectives',headers=h).json()['objectives']
    assert len(rows)==1 and rows[0]['status']=='draft'
    assert rows[0]['source_chunk_ids']==[chunk]
    assert rows[0]['keywords']==['code review','correctness']
    assert rows[0]['starting_scenario']==''
    properties=requests[0]['response_format']['json_schema']['schema']['properties']['objectives']['items']['properties']
    assert 'keywords' in properties and 'title' not in properties and 'starting_scenario' not in properties
    assert chunk in requests[0]['messages'][1]['content']
    path=base+f"/learning-objectives/{rows[0]['objective_id']}"
    approved=client.patch(path,headers=h,json={'status':'approved','success_criteria':['Checks correctness','Explains consistency']})
    assert approved.status_code==200,approved.text
    assert approved.json()['success_criteria']==['Checks correctness','Explains consistency']
    assert client.post(base+f'/documents/{fid}/learning-objectives/generate',headers=h).status_code==202
    kept=client.get(base+'/learning-objectives',headers=h).json()['objectives']
    assert len(kept)==1 and kept[0]['objective_id']==rows[0]['objective_id'] and kept[0]['status']=='approved'
    rejected=client.patch(path,headers=h,json={'status':'rejected'})
    assert rejected.json()['status']=='rejected'
    assert client.post(base+f'/documents/{fid}/learning-objectives/generate',headers=h).status_code==202
    assert client.get(base+'/learning-objectives',headers=h).json()['objectives'][0]['status']=='rejected'


def test_objective_routes_require_managing_instructor(client,roster,monkeypatch):
    fid,did,chunk=material(roster);fake_model(monkeypatch,chunk)
    base=f"/api/courses/{roster['course']}"
    for role in ('student','other_prof'):
        h=roster['headers'][role]
        assert client.get(base+'/learning-objectives',headers=h).status_code==403
        assert client.post(base+f'/documents/{fid}/learning-objectives/generate',headers=h).status_code==403
        assert client.get(base+f'/documents/{fid}/learning-objectives/generation-status',headers=h).status_code==403
        assert client.patch(base+f'/learning-objectives/{uuid4()}',headers=h,json={'status':'approved'}).status_code==403
    h=roster['headers']['prof']
    assert client.post(base+f'/documents/{uuid4()}/learning-objectives/generate',headers=h).status_code==404
    assert client.patch(base+f'/learning-objectives/{uuid4()}',headers=h,json={'status':'approved'}).status_code==404
    assert client.patch(base+f'/learning-objectives/{uuid4()}',headers=h,json={'source_chunk_ids':[chunk]}).status_code==422


def test_generation_failure_and_concurrent_request_preserve_existing_objectives(client,roster,monkeypatch):
    fid,did,chunk=material(roster);db.replace_document_learning_objectives(fid,roster['course'],[candidate(chunk)])
    base=f"/api/courses/{roster['course']}";h=roster['headers']['prof'];path=base+f'/documents/{fid}/learning-objectives/generate'
    async def fail(*args):raise RuntimeError('model unavailable')
    monkeypatch.setattr('platform_app.objectives.extract_and_save_learning_objectives',fail)
    assert client.post(path,headers=h).status_code==202
    assert client.get(path.replace('/generate','/generation-status'),headers=h).json()['status']=='failed'
    assert len(client.get(base+'/learning-objectives',headers=h).json()['objectives'])==1
    with store.connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'objective-generation:{fid}',))
        assert client.post(path,headers=h).status_code==202
        assert client.get(path.replace('/generate','/generation-status'),headers=h).json()['status']=='failed'


def test_objective_selection_freezes_keywords_evidence_and_diagnostic_question(client,roster):
    fid,did,chunk=material(roster)
    otherfid,otherdid,otherchunk=material(roster,'A completely unrelated document about user interfaces.')
    db.replace_document_learning_objectives(fid,roster['course'],[candidate(chunk)])
    obj=db.list_course_learning_objectives(roster['course'])[0]
    item,_=draft(client,roster,config={'document_ids':[did],'learning_objective_id':obj['objective_id']})
    pub=f"/api/platform/assignments/{item['id']}/publish";h=roster['headers']['prof']
    assert client.post(pub,headers=h).status_code==422
    db.update_course_learning_objective(roster['course'],obj['objective_id'],{'status':'approved'})
    published=client.post(pub,headers=h)
    assert published.status_code==200,published.text
    with store.connection() as conn:
        saved=conn.execute('SELECT * FROM assignments_platform WHERE id=%s',(item['id'],)).fetchone()
    snapshot=saved['snapshot'];assert [c['chunk_id'] for c in snapshot['chunks']]==[chunk]
    assert otherchunk not in json.dumps(snapshot)
    db.update_course_learning_objective(roster['course'],obj['objective_id'],{'status':'rejected','keywords':['Changed later']})
    start=client.post(f"/api/platform/assignments/{item['id']}/start",headers=roster['headers']['student'])
    assert start.status_code==200,start.text
    opening=start.json()['messages'][0]['content']
    assert 'code review' in opening
    assert 'A reviewer checks correctness and consistency before a change enters the codebase.' in opening
    assert opening.endswith('What should a reviewer check, and why?')
    assert start.json()['engine_state']['socratic']['objective_keywords']==['code review','correctness']
    assert start.json()['engine_state']['socratic']['stable_concept']=='code review, correctness'
    with store.connection() as conn:
        saved=conn.execute('SELECT snapshot FROM assignments_platform WHERE id=%s',(item['id'],)).fetchone()['snapshot']
    assert saved['learning_objective']['status']=='approved'
    assert saved['learning_objective']['keywords']==['code review','correctness']


def test_cross_course_objective_and_unsupported_document_cannot_publish(client,roster):
    fid,did,chunk=material(roster);otherfid,otherdid,otherchunk=material(roster,'Unrelated evidence.')
    db.replace_document_learning_objectives(fid,roster['course'],[candidate(chunk)])
    obj=db.list_course_learning_objectives(roster['course'])[0]
    db.update_course_learning_objective(roster['course'],obj['objective_id'],{'status':'approved'})
    assignment={'tool':'socratic','course_id':roster['course'],'config':{'document_ids':[otherdid],'learning_objective_id':obj['objective_id']}}
    with pytest.raises(HTTPException,match='supporting document'):engines.publish_snapshot(assignment)
    assert db.get_approved_learning_objective(str(uuid4()),obj['objective_id']) is None


def test_deleting_document_cascades_objectives_without_changing_published_snapshot(client,roster):
    fid,did,chunk=material(roster);db.replace_document_learning_objectives(fid,roster['course'],[candidate(chunk)])
    assert db.list_course_learning_objectives(roster['course'])
    response=client.delete(f"/api/courses/{roster['course']}/documents/{fid}",headers=roster['headers']['prof'])
    assert response.status_code==200,response.text
    assert db.list_course_learning_objectives(roster['course'])==[]


def test_keyword_updates_are_validated_and_old_scenario_fields_are_not_editable(client,roster):
    fid,did,chunk=material(roster)
    db.replace_document_learning_objectives(fid,roster['course'],[candidate(chunk)])
    obj=db.list_course_learning_objectives(roster['course'])[0]
    path=f"/api/courses/{roster['course']}/learning-objectives/{obj['objective_id']}";h=roster['headers']['prof']
    updated=client.patch(path,headers=h,json={'keywords':[' code review ','Code Review',' correctness ']})
    assert updated.status_code==200,updated.text
    assert updated.json()['keywords']==['code review','correctness']
    for body in [{'keywords':[]},{'keywords':[' ']},{'keywords':['x'*121]},{'title':'Old title'},{'starting_scenario':'A mandatory scenario'}]:
        assert client.patch(path,headers=h,json=body).status_code==422


def test_keywords_backfill_preserves_reviewed_legacy_rows(roster):
    from pathlib import Path
    from uuid import UUID
    fid,did,chunk=material(roster)
    oid=uuid4()
    with store.connection() as conn:
        conn.execute("""INSERT INTO learning_objectives_platform
            (id,course_id,file_id,title,objective_text,starting_scenario,diagnostic_question,source_chunk_ids,evidence_type,confidence,status)
            VALUES (%s,%s,%s,'Legacy review topic','Explain code review.','Legacy saved scenario','What should a reviewer check?','[]','explicit',.9,'approved')""",(oid,roster['course'],fid))
        conn.execute((Path(__file__).parents[1]/'platform_app/migrations/009_objective_keywords.sql').read_text())
        row=conn.execute('SELECT keywords,status,starting_scenario FROM learning_objectives_platform WHERE id=%s',(oid,)).fetchone()
    assert row['keywords']==['Legacy review topic']
    assert row['status']=='approved'
    assert row['starting_scenario']=='Legacy saved scenario'


def test_new_keywords_objective_does_not_reuse_an_old_predefined_scenario():
    objective={**candidate('chunk-1'),'objective_id':str(uuid4()),'starting_scenario':'Never force this saved example.'}
    result=engines.start({'tool':'socratic','snapshot':{'config':{},'learning_objective':objective}}, {})
    assert result['messages']==[{'role':'assistant','content':objective['diagnostic_question']}]
    assert result['socratic']['stable_concept']=='code review, correctness'
    assert result['socratic']['objective_keywords']==['code review','correctness']


def test_legacy_published_snapshot_keeps_its_published_opening():
    objective={'title':'Existing review topic','objective':'Explain review.','starting_scenario':'Alex asks Sam for a review.',
        'diagnostic_question':'What should Sam check?','objective_id':str(uuid4())}
    result=engines.start({'tool':'socratic','snapshot':{'config':{},'learning_objective':objective}}, {})
    assert result['messages'][0]['content']=='Alex asks Sam for a review.\n\nWhat should Sam check?'


def test_keyword_scope_blocks_unrelated_questions_before_retrieval_and_scoring(monkeypatch):
    import asyncio
    from app.classifier import MessageClassification
    assignment={'id':uuid4(),'snapshot':{'config':{},'learning_objective':{'keywords':['code review']},'chunks':[]}}
    attempt={'id':uuid4(),'messages':[],'engine_state':{'socratic':{'objective_keywords':['student injected keyword']}}}
    async def classify(*args,**kwargs):
        assert kwargs['allowed_keywords']==('code review',)
        return MessageClassification(message_role='learning_question',keyword_scope_match=False,target_concepts=('SQL joins',),source='llm')
    monkeypatch.setattr(engines,'classify_message',classify)
    def forbidden(*args,**kwargs): raise AssertionError('Outside-scope request reached retrieval/scoring/generation')
    monkeypatch.setattr(engines,'_retrieve_assignment_sources',forbidden)
    monkeypatch.setattr(engines,'evaluate_student_answer',forbidden)
    monkeypatch.setattr(engines.rag,'generate_answer',forbidden)
    result=asyncio.run(engines._socratic_message(assignment,attempt,'Explain SQL joins'))
    assert result['sources']==[] and result['socratic']['last_score'] is None
    assert result['socratic']['keywords']==['code review']
    assert 'code review' in result['reply'] and 'SQL joins' not in result['reply']


def test_keyword_scope_is_not_bypassed_when_classifier_fails(monkeypatch):
    import asyncio
    from app.classifier import MessageClassification
    assignment={'id':uuid4(),'snapshot':{'config':{},'learning_objective':{'keywords':['code review']},'chunks':[]}}
    attempt={'id':uuid4(),'messages':[],'engine_state':{}}
    async def classify(*args,**kwargs): return MessageClassification(source='rules')
    monkeypatch.setattr(engines,'classify_message',classify)
    with pytest.raises(HTTPException) as error:
        asyncio.run(engines._socratic_message(assignment,attempt,'Explain SQL joins'))
    assert error.value.status_code==503


def test_keyword_scope_passes_full_list_to_retrieval_evaluation_and_tutoring(monkeypatch):
    import asyncio
    from app.classifier import MessageClassification
    from app.schemas import Source
    keywords=['code review','correctness','a long keyword phrase '+ 'x'*100]
    seen={}
    async def classify(*args,**kwargs):
        seen['classify']=kwargs
        return MessageClassification(message_role='student_answer',keyword_scope_match=True,target_concepts=('unapproved model label',),source='llm')
    def retrieve(query,chunks,extra_queries=()):
        seen['queries']=[query,*extra_queries]
        return [Source(document_id='doc',chunk_id='chunk',title='Notes',text='Code review checks correctness.',score=1)]
    async def evaluate(*args,**kwargs): seen['evaluate']=kwargs;return None
    async def generate(*args,**kwargs): seen['generate']=kwargs;return 'How does review help catch an error?'
    async def resolve(*args,**kwargs):return None
    monkeypatch.setattr(engines,'classify_message',classify)
    monkeypatch.setattr(engines,'_retrieve_assignment_sources',retrieve)
    monkeypatch.setattr(engines,'evaluate_student_answer',evaluate)
    monkeypatch.setattr(engines.rag,'generate_answer',generate)
    monkeypatch.setattr(engines,'resolve_term',resolve)
    assignment={'id':uuid4(),'snapshot':{'config':{},'learning_objective':{'keywords':keywords},'chunks':[]}}
    attempt={'id':uuid4(),'messages':[{'role':'assistant','content':'Why review a change?'}],'engine_state':{}}
    result=asyncio.run(engines._socratic_message(assignment,attempt,'Another person can catch mistakes.'))
    assert all(seen[stage]['allowed_keywords']==tuple(keywords) for stage in ['classify','evaluate','generate'])
    assert all(all(word in query for word in keywords) for query in seen['queries'])
    assert result['socratic']['keywords']==keywords
    assert 'unapproved model label' not in result['socratic']['keywords']


def test_socratic_publish_requires_an_approved_keyword_scope(client,roster):
    fid,did,chunk=material(roster)
    item,_=draft(client,roster,config={'document_ids':[did]})
    result=client.post(f"/api/platform/assignments/{item['id']}/publish",headers=roster['headers']['prof'])
    assert result.status_code==422
    assert 'saved keywords' in result.json()['detail']


def test_single_assignment_keyword_box_saves_and_freezes_scope_without_an_objective(client,roster):
    fid,did,chunk=material(roster)
    otherfid,otherdid,otherchunk=material(roster,'Review discussion also shares knowledge between engineers.')
    item,body=draft(client,roster,config={'keywords':[' code review ','CODE REVIEW','knowledge sharing'],'document_ids':[]})
    assert item['config']['keywords']==['code review','knowledge sharing']
    assert not item['config']['learning_objective_id']
    path=f"/api/platform/assignments/{item['id']}";headers=roster['headers']['prof']
    confirmed=client.post(path+'/keywords/confirm',headers=headers)
    assert confirmed.status_code==200,confirmed.text
    published=client.post(path+'/publish',headers=headers)
    assert published.status_code==200,published.text
    with store.connection() as conn:
        snapshot=conn.execute('SELECT snapshot FROM assignments_platform WHERE id=%s',(item['id'],)).fetchone()['snapshot']
    assert snapshot['approved_keywords']==['code review','knowledge sharing']
    assert client.get(path,headers=headers).json()['config']['keywords']==['code review','knowledge sharing']
    assert snapshot['learning_objective'] is None
    assert {item['chunk_id'] for item in snapshot['chunks']}=={chunk,otherchunk}
    started=client.post(path+'/start',headers=roster['headers']['student'])
    assert started.status_code==200,started.text
    opening=started.json()['messages'][0]['content']
    assert 'code review' in opening
    assert 'A reviewer checks correctness and consistency before a change enters the codebase.' in opening
    assert opening.endswith('how does it relate to code review?')
    assert started.json()['engine_state']['socratic']['objective_keywords']==['code review','knowledge sharing']
    assert client.put(path,headers=headers,json={**body,'config':{'keywords':['unrelated edit']}}).status_code==409
    assert snapshot['approved_keywords']==list(engines._assignment_keywords(snapshot))


def test_assignment_keyword_validation_rejects_blank_and_excess_values(client,roster):
    body=dict(course_id=roster['course'],tool='socratic',title='Keywords',audience='course')
    for words in [[' '],['x'*121],[str(i) for i in range(9)]]:
        response=client.post('/api/platform/assignments',headers=roster['headers']['prof'],json={**body,'config':{'keywords':words}})
        assert response.status_code==422,response.text


def test_first_student_question_is_kept_for_keyword_only_assignment(monkeypatch):
    import asyncio
    from app.classifier import MessageClassification
    async def classify(*args,**kwargs):
        return MessageClassification(keyword_scope_match=True,source='llm',target_concepts=('code review',))
    async def resolve(*args,**kwargs): return None
    async def evaluate(*args,**kwargs): return None
    async def generate(*args,**kwargs): return 'Why might another reader notice a mistake?'
    monkeypatch.setattr(engines,'classify_message',classify)
    monkeypatch.setattr(engines,'resolve_term',resolve)
    monkeypatch.setattr(engines,'evaluate_student_answer',evaluate)
    monkeypatch.setattr(engines.rag,'generate_answer',generate)
    monkeypatch.setattr(engines,'_retrieve_assignment_sources',lambda *args:[])
    assignment={'id':uuid4(),'snapshot':{'config':{'keywords':['code review']},'approved_keywords':['code review'],'chunks':[]}}
    attempt={'id':uuid4(),'messages':[],'engine_state':{'socratic':engines.start({'tool':'socratic',**assignment},{})['socratic']}}
    result=asyncio.run(engines._socratic_message(assignment,attempt,'What is code review?'))
    assert result['socratic']['original_question']=='What is code review?'
    assert result['socratic']['keywords']==['code review']

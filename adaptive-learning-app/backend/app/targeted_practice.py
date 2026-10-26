"""Optional, concept-scoped practice after a bounded quiz; never changes quiz marks."""
import re

from .openai_client import assess_configured_response


def _text(value):
    return re.sub(r'\W+', ' ', value.casefold()).strip()


def _candidates(plan, question):
    asset = next((item for item in plan['learning_assets'] if item['objective_id'] == question['objective_id']), {})
    quiz_prompts = {_text(item['question']) for item in plan['diagnostic_quiz']}
    result, seen = [], set()
    for level in ('foundational', 'standard', 'accelerated'):
        for index, item in enumerate(asset.get(level, [])):
            prompt = item.get('prompt', '').strip()
            key = _text(prompt)
            example = item.get('worked_example') or question.get('worked_example') or asset.get('worked_example')
            if (item.get('concept') != question['concept'] or not prompt or not item.get('rubric')
                    or not example or key in quiz_prompts or key in seen or key == _text(example)):
                continue
            seen.add(key)
            result.append({**item, 'id': f"{question['id']}:{level}:{index}", 'worked_example': example})
    return result


def start_review(state):
    plan = state['lesson_snapshot']
    items, seen = [], set()
    for question in plan['diagnostic_quiz']:
        attempts = state.get('quiz_attempts', {}).get(question['id'], [])
        key = (question['objective_id'], question['concept'])
        if not attempts or attempts[0]['correct'] or key in seen:
            continue
        seen.add(key)
        candidates = _candidates(plan, question)
        items.append({'question_id': question['id'], 'objective_id': question['objective_id'],
                      'concept': question['concept'], 'status': 'available' if candidates else 'unavailable',
                      'activities': candidates[:2], 'used': [], 'history': []})
    state.update(review_items=items, review_activity=None)
    if not items:
        return False
    state['stage'] = 'quiz_review'
    return True


def public_review(state):
    items = [{**{key: item[key] for key in ('question_id', 'concept', 'status')}, 'has_more': any(activity['id'] not in item['used'] for activity in item['activities'])} for item in state.get('review_items', [])]
    activity = state.get('review_activity')
    return {'items': items, 'activity': {key: activity[key] for key in ('id', 'question_id', 'concept', 'prompt', 'answered')} if activity else None}


def process_review(state, turn, enter_application):
    items = state.get('review_items', [])
    if turn.action == 'continue':
        for item in items:
            if item['status'] in {'available', 'in_progress'}:
                item['status'] = 'skipped'
        state['review_activity'] = None
        return state, enter_application(state), None
    current = state.get('review_activity')
    if turn.action == 'choice':
        item = next((item for item in items if item['question_id'] == turn.content), None)
        if not item or item['status'] not in {'available', 'practiced', 'needs_review'}:
            raise ValueError('Choose one of the available practice topics, or continue to the application task.')
        if current and not current['answered']:
            raise ValueError('Answer the current practice question, skip it, or continue to the application task.')
        activity = next((candidate for candidate in item['activities'] if candidate['id'] not in item['used']), None)
        if not activity:
            return state, 'You have tried the available examples for this concept. Choose another topic or continue to the application task.', None
        item['used'].append(activity['id'])
        item['status'] = 'in_progress'
        state['review_activity'] = {**activity, 'question_id': item['question_id'], 'objective_id': item['objective_id'], 'concept': item['concept'], 'answered': False, 'attempts': 0, 'assistance': ['worked_example']}
        return state, (f"Let’s practice {item['concept']}. Your original quiz score stays the same.\n\n"
                       f"Worked example (a related case):\n{activity['worked_example']}\n\n"
                       f"Now try a different case:\n{activity['prompt']}\n\nType your reasoning, or continue to the application task whenever you prefer."), None
    if not current:
        return state, 'Choose a concept to practice, or continue to the application task. This practice is optional and does not change your quiz score.', None
    item = next(item for item in items if item['question_id'] == current['question_id'])
    if turn.question_id and turn.question_id != current['id']:
        raise ValueError('Please respond to the current practice question.')
    if current['answered']:
        return state, 'Choose another practice example or continue to the application task.', None
    if turn.action == 'message' and turn.content.casefold().strip() in {"skip", "i don't know", "i don’t know"}:
        current['answered'] = True
        item['status'] = 'needs_review'
        item['history'].append({'activity_id': current['id'], 'status': 'skipped', 'assisted': True})
        return state, 'That’s okay. You can revisit this concept in the readings, choose another example, or continue to the application task.', None
    if turn.action == 'hint':
        current['assistance'].append('hint')
        return state, 'Hint: ' + current.get('hint', '') + '\n\nYou can try your reasoning or continue to the application task.', None
    if turn.action != 'answer' or not turn.content.strip():
        return state, 'Type your reasoning for the practice question, ask for a hint, or continue to the application task.', None
    plan = state['lesson_snapshot']
    objective = next(obj for obj in plan['objectives'] if obj['id'] == current['objective_id'])
    assessment = assess_configured_response(turn.content, current['rubric'], objective, plan['approved_material'], current['prompt'])
    if assessment.get('status') in {'grader_unavailable', 'grader_error'}:
        return state, 'Practice feedback is temporarily unavailable. Your response is saved in this conversation and has not been marked wrong. Retry your response or continue to the application task.', None
    current['attempts'] += 1
    sound = assessment.get('category') == 'sound_reasoning'
    item['history'].append({'activity_id': current['id'], 'response': turn.content, 'assessment': assessment, 'assistance': list(current['assistance']), 'assisted': True})
    current['answered'] = sound or current['attempts'] >= 2
    item['status'] = 'practiced' if sound else 'needs_review' if current['answered'] else 'in_progress'
    next_step = ('Choose another topic or continue to the application task.' if current['answered'] else 'You can revise your reasoning, ask for a hint, skip this practice question, or continue to the application task.')
    return state, assessment['feedback'] + '\n\n' + next_step + '\n\nThis is supported practice; your first-attempt quiz score is unchanged.', None

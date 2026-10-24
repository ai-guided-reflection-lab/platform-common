"""Bounded SDL lessons: prerequisites, study, supported quiz, application, finish.

The authored snapshot controls content and keys. Assistance is recorded without
deductions; quiz_score counts first-attempt correct answers out of five.
"""
from .openai_client import assess_configured_response
from uuid import uuid4


def introduction(plan):
    if plan.get('prerequisite_message', '').strip():
        return plan['prerequisite_message']
    return (f"Today we are learning {plan['topic']}.\n\n"
            f"Starting point: {plan['starting_point']}\n\n"
            f"By the end: {plan['ending_point']}\n\n"
            f"Prerequisites: {plan['prerequisite_knowledge']}\n\n"
            + ("Read the prerequisite links below if needed. " if plan.get("prerequisite_resources") else "Review these prerequisite assumptions with your course material or instructor if needed. ")
            + "Confirm you are familiar with these prerequisites to continue.")


def process_turn(state, turn):
    from .lesson_flow import normalize, ready, parse_option, support_message
    plan = state['lesson_snapshot']
    text = normalize(turn.content).rstrip('.!?')
    stage = state['stage']
    if stage == 'completed':
        raise ValueError('This lesson is complete.')
    if turn.action == 'pause':
        if stage != 'paused':
            state['resume_stage'] = stage
        state['stage'] = 'paused'
        return state, 'Paused. Your progress is saved.', None
    if stage == 'paused':
        if turn.action != 'resume':
            return state, 'Choose Resume to continue.', None
        state['stage'] = state.pop('resume_stage', 'welcome')
        return state, 'Welcome back. Continue from where you paused.', None
    if stage == 'welcome':
        if turn.action != 'continue':
            return state, 'Review the prerequisite readings, then select “I’m familiar with the prerequisites”.', None
        state.update(prerequisites_confirmed=True, stage='study_resources')
        if plan.get('study_message', '').strip():
            return state, plan['study_message'], None
        return state, (f"Let's study {plan['topic']}.\n\n{plan['topic_introduction']}\n\n"
                       f"Worked example: {plan['introductory_example']}\n\n"
                       'Explore the topic readings below. Ask for examples, or start the quiz when ready.'), None
    if stage == 'study_resources':
        if text in {'explain with an example', 'please explain with an example'}:
            examples = '\n\n'.join(
                f"{objective['title']}\n{asset['explanation']}\n\nWorked example: {asset['worked_example']}"
                for objective in plan['objectives']
                for asset in plan['learning_assets'] if asset['objective_id'] == objective['id']
            )
            return state, examples + '\n\nWhat would you like to clarify? You can ask a question, revisit the readings, or start the quiz when you feel ready.', None
        if turn.action == 'continue' or ready(turn.content):
            state.update(stage='diagnostic_quiz', quiz_attempts={}, quiz_score=0)
            return state, "Okay, let’s take a small quiz based on the topics we just studied.", None
        return state, support_message(plan, state, turn.content), None
    if stage == 'diagnostic_quiz':
        index = state['quiz_index']
        question = plan['diagnostic_quiz'][index]
        if turn.question_id and turn.question_id != question['id']:
            raise ValueError('Please answer the current question.')
        attempts = state.setdefault('quiz_attempts', {}).setdefault(question['id'], [])
        if turn.action == 'hint' or text == 'read more':
            kind = 'worked_example_hint' if turn.action == 'hint' else 'reading'
            state['assistance'].setdefault(question['id'], []).append(kind)
            asset = next(a for a in plan['learning_assets'] if a['objective_id'] == question['objective_id'])
            if turn.action == 'hint':
                reply = f"Hint: {question['hint']}\n\nWorked example (a related case): {question.get('worked_example') or asset['worked_example']}"
            else:
                reply = f"Review: {question['material_reference']}\n\n{asset['explanation']}\n\nUse the topic reading links below, then retry."
            return state, reply, None
        try:
            option = turn.option_index if turn.option_index is not None else parse_option(turn.content, question)
        except ValueError as exc:
            return state, str(exc), None
        correct = option == question['correct_index']
        record = {'question_id': question['id'], 'option_index': option, 'correct': correct,
                  'confidence': turn.confidence, 'explanation': turn.explanation,
                  'assistance': list(state['assistance'].get(question['id'], []))}
        attempts.append(record)
        resolved = correct or len(attempts) >= 3
        state.setdefault('quiz_feedback', []).append({
            'turn_id': turn.turn_id, 'question_id': question['id'], 'question_index': index,
            'question': question['question'], 'options': list(question['options']),
            'selected_index': option, 'confidence': turn.confidence, 'correct': correct,
            'resolved': resolved, 'correct_index': question['correct_index'] if resolved else None,
        })
        if len(attempts) == 1 and correct:
            state['quiz_score'] += 1
        if not correct and len(attempts) < 3:
            state['quiz_retry'] = True
            misconception = question['distractor_misconceptions'][option] if option is not None else ''
            state['assistance'].setdefault(question['id'], []).append('feedback_hint')
            return state, (f"Not quite. {misconception}\n\n"
                           f"A small hint: {question['hint']}\n\n"
                           "You can try another option, read more, or ask for a worked example."), None
        state['diagnostic'].append({**record, 'objective_id': question['objective_id'],
                                    'concept': question['concept'], 'attempt_count': len(attempts),
                                    'question': question['question'], 'correct_index': question['correct_index'],
                                    'explanation_of_answer': question['explanation'], 'reasoning': {},
                                    'assistance_used': bool(record['assistance'])})
        state['quiz_retry'] = False
        state['quiz_index'] += 1
        feedback = ('Correct. ' if correct else 'Let’s look at this together. The correct answer is '
                    + question['options'][question['correct_index']] + '. ') + question['explanation']
        if state['quiz_index'] < 5:
            return state, feedback + '\n\nLet’s try the next question.', None
        state.update(stage='application', diagnostic_complete=True)
        requirements = '\n'.join(f"• {criterion['description']}" for criterion in plan['application_rubric'])
        return state, (feedback + f"\n\nYou scored {state['quiz_score']}/5 on your first attempts.\n\n"
                       "Now let’s do an application task.\n"
                       f"{plan['required_task']['submission_prompt']}\n\nInclude in your response:\n{requirements}\n\nType your response."), None
    if stage == 'application':
        if turn.action != 'answer' or not turn.content.strip():
            return state, 'Type your application response and select Submit final response.', None
        objective = {'title': plan['topic'], 'description': plan['ending_point']}
        requirements = '\n'.join(f"{index + 1}. {criterion['description']}" for index, criterion in enumerate(plan['application_rubric']))
        assessment = assess_configured_response(turn.content, plan['application_rubric'], objective,
                                                plan['approved_material'], plan['required_task']['submission_prompt'] + '\n\nVisible assessment requirements:\n' + requirements, feedback_sections=True)
        if assessment.get('status') in {'grader_unavailable', 'grader_error'}:
            return state, 'Feedback is temporarily unavailable. Your response is saved in this conversation; retry your submission when the grader is available.', None
        state.update(stage='completed', application_submission=turn.content, application_assessment=assessment,
                     completion_code='SDL-' + uuid4().hex.upper())
        return state, (f"What you got right\n{assessment['what_went_well']}\n\n"
                       f"What you got wrong\n{assessment['what_was_incorrect']}\n\n"
                       f"How to improve\n{assessment['how_to_improve']}\n\n"
                       'Lesson complete.'), None
    raise ValueError('This learning stage is not available.')

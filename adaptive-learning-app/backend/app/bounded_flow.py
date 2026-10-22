"""Bounded SDL lessons: prerequisites, study, supported quiz, application, finish.

The authored snapshot controls content and keys. Assistance is recorded without
deductions; quiz_score counts first-attempt correct answers out of five.
"""
from .openai_client import assess_configured_response


def introduction(plan):
    return (f"Today we are learning {plan['topic']}.\n\n"
            f"Starting point: {plan['starting_point']}\n\n"
            f"By the end: {plan['ending_point']}\n\n"
            f"Prerequisites: {plan['prerequisite_knowledge']}\n\n"
            "Read the prerequisite links below if needed. Confirm you are familiar with these prerequisites to continue.")


def process_turn(state, turn):
    from .lesson_flow import normalize, ready, question_message, parse_option, support_message
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
        return state, (f"Let's study {plan['topic']}.\n\n{plan['topic_introduction']}\n\n"
                       f"Worked example: {plan['introductory_example']}\n\n"
                       'Explore the topic readings below. Ask for examples, or start the quiz when ready.'), None
    if stage == 'study_resources':
        if turn.action == 'continue' or ready(turn.content):
            state.update(stage='diagnostic_quiz', quiz_attempts={}, quiz_score=0)
            return state, ('Five questions, with up to three attempts each. Your score records first-attempt answers; '
                           'help use is recorded without deductions.\n\n' + question_message(plan, 0)), None
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
                reply = f"Hint: {question['hint']}\n\nWorked example (a related case): {asset['worked_example']}"
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
        if len(attempts) == 1 and correct:
            state['quiz_score'] += 1
        if not correct and len(attempts) < 3:
            state['quiz_retry'] = True
            misconception = question['distractor_misconceptions'][option] if option is not None else ''
            return state, (f"That is not correct. {misconception}\n\n"
                           f"{3 - len(attempts)} attempts remaining. Choose Read more or Get a hint / worked example, or retry."), None
        state['diagnostic'].append({**record, 'objective_id': question['objective_id'],
                                    'concept': question['concept'], 'attempt_count': len(attempts),
                                    'question': question['question'], 'correct_index': question['correct_index'],
                                    'explanation_of_answer': question['explanation'], 'reasoning': {},
                                    'assistance_used': bool(record['assistance'])})
        state['quiz_retry'] = False
        state['quiz_index'] += 1
        feedback = ('Correct. ' if correct else 'Three attempts used. The correct answer is '
                    + question['options'][question['correct_index']] + '. ') + question['explanation']
        if state['quiz_index'] < 5:
            return state, feedback + '\n\n' + question_message(plan, state['quiz_index']), None
        state.update(stage='application', diagnostic_complete=True)
        return state, (feedback + f"\n\nQuiz complete: {state['quiz_score']}/5 on first attempts.\n\n"
                       f"Final application task: {plan['required_task']['submission_prompt']}\n\n"
                       'Type your response. You have one submission, followed by feedback.'), None
    if stage == 'application':
        if turn.action != 'answer' or not turn.content.strip():
            return state, 'Type your application response and select Submit final response.', None
        objective = {'title': plan['topic'], 'description': plan['ending_point']}
        assessment = assess_configured_response(turn.content, plan['application_rubric'], objective,
                                                plan['approved_material'], plan['required_task']['submission_prompt'])
        if assessment.get('status') in {'grader_unavailable', 'grader_error'}:
            return state, 'Feedback is temporarily unavailable. Your response is saved in this conversation; retry your submission when the grader is available.', None
        state.update(stage='completed', application_submission=turn.content, application_assessment=assessment)
        return state, (f"Application feedback: {assessment['feedback']}\n\n"
                       f"Intended outcome: {plan['ending_point']}\n\n"
                       'Lesson complete. This records completion; the feedback shows how your response addressed the outcome.'), None
    raise ValueError('This learning stage is not available.')

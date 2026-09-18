"""Message graph — runs once per POST /api/chat/message."""

from langgraph.graph import StateGraph, END

from app.agents.state import ReflectionState
from app.agents.nodes.context import inject_context
from app.agents.nodes.tutor import call_tutor
from app.agents.nodes.evaluator import evaluate_reply
from app.agents.nodes.planner import route_phase, bonus_transition


def build_message_graph() -> StateGraph:
    graph = StateGraph(ReflectionState)

    graph.add_node("inject_context", inject_context)
    graph.add_node("call_tutor", call_tutor)
    graph.add_node("evaluate_reply", evaluate_reply)
    graph.add_node("bonus_transition", bonus_transition)

    graph.set_entry_point("inject_context")
    graph.add_edge("inject_context", "call_tutor")
    graph.add_edge("call_tutor", "evaluate_reply")

    graph.add_conditional_edges(
        "evaluate_reply",
        route_phase,
        {"bonus_transition": "bonus_transition", "end": END},
    )
    graph.add_edge("bonus_transition", END)

    return graph

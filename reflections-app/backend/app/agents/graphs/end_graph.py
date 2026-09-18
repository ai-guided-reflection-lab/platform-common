"""End graph — runs once on POST /api/chat/end."""

from langgraph.graph import StateGraph, END

from app.agents.state import ReflectionState
from app.agents.nodes.session import format_transcript
from app.agents.nodes.evaluator import evaluate_session


def build_end_graph() -> StateGraph:
    graph = StateGraph(ReflectionState)

    graph.add_node("format_transcript", format_transcript)
    graph.add_node("evaluate_session", evaluate_session)

    graph.set_entry_point("format_transcript")
    graph.add_edge("format_transcript", "evaluate_session")
    graph.add_edge("evaluate_session", END)

    return graph

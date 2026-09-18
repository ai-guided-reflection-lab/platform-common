"""Init graph — runs once on POST /api/chat/start."""

from langgraph.graph import StateGraph, END

from app.agents.state import ReflectionState
from app.agents.nodes.context import load_context
from app.agents.nodes.planner import generate_questions
from app.agents.nodes.session import build_session


def build_init_graph() -> StateGraph:
    graph = StateGraph(ReflectionState)

    graph.add_node("load_context", load_context)
    graph.add_node("generate_questions", generate_questions)
    graph.add_node("build_session", build_session)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "generate_questions")
    graph.add_edge("generate_questions", "build_session")
    graph.add_edge("build_session", END)

    return graph

from typing import Annotated, TypedDict
from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.tools import calculator
from app.core.config import get_settings


class MessageState(TypedDict):
    messages: Annotated[list, add_messages]


def create_agent_graph(checkpointer=None):
    settings = get_settings()

    # Streaming is enabled for Time to First Token (TTFT) tracking
    llm = ChatOpenAI(
        model=settings.MODEL_NAME,
        api_key=settings.OPENAI_API_KEY,
        streaming=True,
    )
    llm_with_tool = llm.bind_tools([calculator])

    system_message = SystemMessage(
        content=(
            "You are a helpful production AI assistant equipped with memory and a calculator tool. "
            "Always use the calculator tool when performing mathematical computations."
        )
    )

    async def chat_node_with_tool(state: MessageState) -> dict:
        response = await llm_with_tool.ainvoke([system_message] + state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessageState)
    builder.add_node("chat_node_with_tool", chat_node_with_tool)
    builder.add_node("tools", ToolNode([calculator]))

    builder.add_edge(START, "chat_node_with_tool")
    builder.add_conditional_edges("chat_node_with_tool", tools_condition)
    builder.add_edge("tools", "chat_node_with_tool")

    cp = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(checkpointer=cp)

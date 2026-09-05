import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


from typing import TypedDict


load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")


class State(TypedDict):
    graph_state: str
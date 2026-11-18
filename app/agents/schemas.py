from typing import Annotated, Literal, TypedDict, List
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
import operator

class Leg(BaseModel):
    mode: Literal["train", "bus", "flight"]
    source: str | None = None
    destination: str | None = None
    date: str | None = Field(None, description="YYYY-MM-DD")
    train_number: str | None = None


class SuperVisorAction(BaseModel):
    action: Literal["run_legs", "ask_user", "finish"]
    legs: List[Leg] = Field(default_factory=list)
    message: str | None = Field(
        None,
        description=(
            "Text shown to the user. "
            "If action is 'ask_user': one short question asking for the missing detail. "
            "If action is 'finish': the complete final answer, using only facts from the agent results. "
            "If action is 'run_legs': leave this null."
        ),
    )


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    next: str
    legs: list[dict]
    
    results: Annotated[list[dict], operator.add]
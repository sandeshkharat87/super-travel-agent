from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send


from app.agents.myAgents import llm as _llm
from app.agents.prompts import _prompt_supervisor
from app.agents.schemas import AgentState, RouteSupeVisor
from app.agents.myAgents import AGENT
IST = ZoneInfo("Asia/Kolkata")

_temp = [
    # "I want to travel from Delhi to Mumbai on 15th August 2023. Can you help me find the best options?",
    "Want to travel to Pune ",
    # "Give me information about the train number 12138",
    # "Pune to Mumbai by flight, then Mumbai to Nagpur by train",
]



def _build_query(leg):
    print("--- build query ---")
    
    today = datetime.now(IST).strftime("%Y-%m-%d")

    
    if leg.get("train_number"):
        return f"Get information and live status of train number {leg['train_number']}"
    else:
        return (
        f"Find {leg['mode']} options from {leg['source']} to {leg['destination']}. "
        f"Date: {leg.get('date') or 'not specified, use today'}."
    )



def dispatch(state):
    print("--- dispatch ---")
    
    if state['needs_clarification'] or not state.get('legs'):
        return END

    op = []
    
    for idx, leg in enumerate(state['legs']):
        op.append( Send(node="leg_node", arg={"idx":idx, "leg":leg })   )
    
    return op


def leg_node(payload: dict):
    print("--- leg node ---")
    
    leg = payload["leg"]
    out = AGENT[leg["mode"]].invoke(
        {"messages": [{"role": "user", "content": _build_query(leg)}]}
    )
    return {"results": [{
        "idx": payload["idx"],
        "mode": leg["mode"],
        "source": leg.get("source"),
        "destination": leg.get("destination"),
        "text": out["messages"][-1].content,
    }]}
    

def router_node(state: AgentState):
    print("--- router node ---")
    
    
    today = datetime.now(IST).strftime("%Y-%m-%d (%A)")
    router = _llm.with_structured_output(RouteSupeVisor, method="json_schema")
    resp = router.invoke([
        SystemMessage(content=f"{_prompt_supervisor}\nToday (IST): {today}"),
        HumanMessage(content=state["msgs"]),
    ])
    return {
        "legs": [leg.model_dump() for leg in resp.legs],
        "needs_clarification": resp.needs_clarification,
        "clarification_question": resp.clarification_question,
    }


def synthesize_node(state: AgentState):
    results = sorted(state["results"], key=lambda r: r["idx"])
    parts = "\n\n".join(
        f"Leg {r['idx'] + 1} [{r['mode']}]"
        + (f" {r['source']} -> {r['destination']}" if r.get("source") else "")
        + f"\n{r['text']}"
        for r in results
    )
    resp = _llm.invoke([
        SystemMessage(content=(
            "You combine travel search results into one clear answer for the user. "
            "Use ONLY facts present in the results. Never invent timings, fares or "
            "availability. If a leg returned nothing or an error, say so. "
            "Keep the legs in order."
        )),
        HumanMessage(content=f"User request: {state['msgs']}\n\nResults:\n{parts}"),
    ])
    return {"answer": resp.content}


workflow = StateGraph(AgentState)
workflow.add_node("router_node", router_node)
workflow.add_node("leg_node", leg_node)
workflow.add_node("synthesize_node", synthesize_node)


workflow.add_edge(START, "router_node")
workflow.add_conditional_edges("router_node", dispatch, ["leg_node", END])
workflow.add_edge("leg_node", "synthesize_node")
workflow.add_edge("synthesize_node", END)   

graph = workflow.compile()



if __name__ == "__main__":
    for q in _temp:
        out = graph.invoke({"msgs": q})
        print("\nQ:", q)
        if out.get("needs_clarification"):
            print("ASK:", out["clarification_question"])
            continue
        print(out["answer"])
        print("=" * 30)
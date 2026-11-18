from datetime import datetime
from zoneinfo import ZoneInfo
from pprint import pprint

from app.agents.myAgents import llm as _llm
from app.agents.schemas import Leg, SuperVisorAction, AgentState
from app.agents.prompts import prompt_supervisor
from langgraph.types import Send
from app.agents.myAgents import AGENT

# 
from langchain_core.messages import AnyMessage, AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver


IST = ZoneInfo("Asia/Kolkata")


def supervisor_node(state):
    print("--- supervisor node ---")
    
    today = datetime.now(IST).strftime("%Y-%m-%d")
    results = state.get("results")

    input_msg = (
        prompt_supervisor.format_messages() 
        + [SystemMessage(content=f"Today Date: {today}")] 
        + state["messages"]
    )
    
    
    if results:
        print("$$$ we got results ")
        rs = sorted(results, key=lambda r: r["idx"])
        input_msg.append(SystemMessage(content="Agent results so far:\n" + "\n\n".join(
            f"[{r['mode']}] {r.get('source') or ''} -> {r.get('destination') or ''}\n{r['text']}"
            for r in rs
        )))
        

    resp = _llm.with_structured_output(SuperVisorAction).invoke(input_msg)
    
    
    if resp.action == "run_legs":
        return {"next": "run_legs", "legs": [i.model_dump() for i in resp.legs]}
    
    return {
        "next": resp.action,
        "legs": [],
        "messages": [AIMessage(content=resp.message or "")],
    }    
    

def _build_query(leg):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if leg.get("train_number"):
        return f"Get information and live status for train number {leg['train_number']}. Today is {today}."
    return (
        f"Find {leg['mode']} options from {leg['source']} to {leg['destination']}. "
        f"Date: {leg.get('date') or today} (YYYY-MM-DD)."
    )


def leg_runner(state, mode_of_travel):
    print("--- leg runner ---")
    
    results = []

    print("\n LEEEEEEEEEEEEEEEEEEEEEEEGS")
    print(f"\t {mode_of_travel}")
    print("\n LEEEEEEEEEEEEEEEEEEEEEEEGS")
    
    for idx, single_leg in enumerate(state['legs']):
        if single_leg["mode"] != mode_of_travel:
            continue
                
        output = AGENT[mode_of_travel].invoke({"messages":[_build_query(single_leg)]})
        
        results.append({
            "idx": idx,
            "mode": mode_of_travel,
            "source": single_leg.get("source"),
            "destination": single_leg.get("destination"),
            "text": output["messages"][-1].content,
        })
        
        print(f"\t {results}")

    return {"results": results}
            
    
def train_node(state: AgentState):
    return leg_runner(state, "train")

def bus_node(state: AgentState):
    return leg_runner(state, "bus")

def flight_node(state: AgentState):
    return leg_runner(state, "flight")

def dispatch(state: AgentState):
    if state.get("next") != "run_legs":
        return END
    # only start the workers that have a leg to run
    return [f"{m}_node" for m in dict.fromkeys(l["mode"] for l in state["legs"])]




# ----------------------

workflow = StateGraph(AgentState)
workflow.add_node("supervisor_node", supervisor_node)
workflow.add_node("train_node", train_node)
workflow.add_node("bus_node", bus_node)
workflow.add_node("flight_node", flight_node)

workflow.add_edge(START, "supervisor_node")
workflow.add_conditional_edges(
    "supervisor_node", dispatch,
    ["train_node", "bus_node", "flight_node", END],
)
for n in ("train_node", "bus_node", "flight_node"):
    workflow.add_edge(n,"supervisor_node")      # the loop

graph = workflow.compile(checkpointer=MemorySaver())

_temp_msg = [
    "I want to travel from pune"
]

def chat(question,thread_id):
    cfg = {"configurable": {"thread_id":thread_id }}
    result = graph.invoke({"messages":[question]},config=cfg)
    print(f"[Result] \n {result}  ")
    return result['messages'][-1].content


if __name__ == "__main__":
    # chat("I want to travel from pune to banglore vai train", "t_single")        # 3 legs
    # chat("Pune to Mumbai by train tomorrow", "t_mode")                # 1 train leg, tomorrow's date
    chat("Info about train 12628", "t_number")                        # 1 train leg, train_number only
    chat("What was my train number", "t_number")
    # chat("Pune to Mumbai by flight, then Mumbai to Nagpur by train", "t_multi")

    # chat("Want to travel to Pune", "t_mem")
    # chat("Nagpur", "t_mem")          # same thread_id on purpose
    
    # graph.get_graph().draw_mermaid_png()
    # graph.get_graph().draw_mermaid_png(output_file_path="my_langgraph.png")

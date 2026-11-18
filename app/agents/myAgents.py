import os
from langchain.agents import create_agent
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

import dotenv

dotenv.load_dotenv()

from app.agents.tools import search_buses, search_flights, search_train,train_get_live_status

# llm = ChatGroq(
#     model=os.getenv("LLM_MODEL", "openai/gpt-oss-20b"),
#     temperature=0,
#     max_tokens=2048,
#     timeout=30,
#     max_retries=3,
# )

llm = ChatOllama(model="mimo-v2.6:9b", temperature=0)


TRAIN_PROMPT = """You are a Train agent for Indian travellers.
Tool: search_train(source, destination, date) finds trains between two places.
Rules:
- Pass city names or station codes. Use the date from the request (YYYY-MM-DD).
- Only state details that the tool returned. Never invent timings, coaches or fares.
- If the tool returns nothing or an error, say so plainly.
- You only search; you cannot book tickets."""

BUS_PROMPT = """You are a Bus agent for Indian travellers.
Tool: search_buses(source, destination) searches the web for bus options.
Rules:
- Pass plain city names.
- Summarize briefly: operators, typical timings, fare range, and a booking link if present.
- Don't invent fares or timings that aren't in the results.
- You only search; you cannot book tickets."""

FLIGHT_PROMPT = """You are a Flight agent for Indian travellers.
Tool: search_flights(source, destination) finds current/recent flights.
Rules:
- Pass city names or IATA codes.
- The tool returns current/recent flight data, not a future timetable or fares.
  Say so if the user asks about a future date or prices.
- If the tool returns nothing or an error, say so plainly.
- You only search; you cannot book tickets."""


_train_tools = [search_train,train_get_live_status] 
_bus_tools = [search_buses]
_flight_tools =  [search_flights] 

AGENT = {
    "train": create_agent(llm, tools=_train_tools, system_prompt=TRAIN_PROMPT),
    "bus": create_agent(llm, tools=_bus_tools, system_prompt=BUS_PROMPT),
    "flight": create_agent(llm, tools=_flight_tools, system_prompt=FLIGHT_PROMPT),
}












from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
import os

load_dotenv()
print("Loaded API Key:", os.getenv("OPENAI_API_KEY"))

checkpointer = InMemorySaver()

class WeatherResponse(BaseModel):
    conditions: str

def get_weather(city: str) -> str:
    '''Get the weather of the given city'''
    return f"It's always sunny in {city}"

model = init_chat_model(
    "gpt-4o",
    # "gpt-4o",
    temperature = 0
)
agent = create_react_agent(
    model = model,
    tools = [get_weather],
    prompt = "Never answer questions about weather",
    response_format = WeatherResponse,
    checkpointer = checkpointer
)

# Run the agent
user_input = input("Feel free to talk with me!\n")

config = {"configurable": {"thread_id": "1"}}
fr_response = agent.invoke(
    {"messages": [{"role": "user", "content": user_input}]},
    config  
)
print(fr_response["messages"][-1].content)

user_input = input("Feel free to talk with me!\n")
sd_response = agent.invoke(
    {"messages": [{"role": "user", "content": user_input}]},
    config
)
print(sd_response["structured_response"])
# print(sd_response["messages"][-1].content)



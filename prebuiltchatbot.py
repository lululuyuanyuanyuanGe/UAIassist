from typing import Annotated

from langchain_tavily import TavilySearch
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import BaseMessage, ToolMessage
from langchain.chat_models import init_chat_model

from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt

import os
from dotenv import load_dotenv

load_dotenv()

# make the checkpoint
memory = MemorySaver()

# Define the format of the conversation messages between LLM
class State(TypedDict):
    messages: Annotated[list, add_messages]
    name: str
    birthday: str

graph_builder = StateGraph(State)

@tool
# Note that because we are generating a ToolMessage for a state update, we
# generally require the ID of the corresponding tool call. We can use
# LangChain's InjectedToolCallId to signal that this argument should not
# be revealed to the model in the tool's schema.
def human_assistance(
        query: str,
        name: str,
        birthday: str,
        tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> str:
    """Request assistance from a human"""
    human_response = interrupt(
        {
            "query": query,
            "name": name,
            "birthday": birthday
        }
    )

    # Let the LLM structure the reply using the parse_human_feedback tool
    parsed_response = llm_with_tools.invoke([
        {"role": "user", "content": f"The human replied: {human_response['data']}"},
        {"role": "tool", "tool_call": {
            "name": "parse_human_feedback",
            "args": {
                "text": human_response["data"]
            }
        }}
    ])

    structured = parsed_response.tool_calls[0].args  # e.g. {"correct": "yes"}

    # Handle corrections
    new_name = structured.get("name", name)
    new_birthday = structured.get("birthday", birthday)
    correct = structured.get("correct", "").lower().startswith("y")

    return Command(update={
        "name": new_name,
        "birthday": new_birthday,
        "messages": [
            ToolMessage(
                tool_call_id=tool_call_id,
                name="human_assistance",
                content="Confirmed" if correct else "Corrected info received"
            )
        ]
    })

@tool
def parse_human_feedback(text: str) -> dict:
    """Parse human correction into a structured dictionary with keys like 'correct', 'name', and 'birthday'."""
    # This is only a schema description for the LLM.
    # LangGraph will auto-fill this with LLM's reasoning.
    pass  # Not executed at runtime — LLM fills this tool response.

search_tool = TavilySearch(max_results = 2)
tools = [search_tool, human_assistance, parse_human_feedback]
llm = init_chat_model(
        "gpt-4o"        
        #temperature
        )
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    message = llm_with_tools.invoke(state["messages"])
    # Because we will be inteerrupting during tool execution, 
    # we disable parallel tool calling to avoid reapting any tool invocations 
    # when we resume
    assert len(message.tool_calls) <= 1
    return {"messages": [message]}

def process_tool_output(tool_call, output):
    # Extract only the relevant data
    if tool_call["name"] == "tavily_search":
        if output["results"]:
            first_result = output["results"][0]
            return f"Search result: {first_result['content']}]\nSource: {first_result['url']}"
        return "No results found."
        # add other tools here if needed
    return str(output) # Fallback

class CustomToolNode(ToolNode):
    def _postprocess(self, tool_call, output):
        return process_tool_output(tool_call, output)

graph_builder.add_node("chatbot", chatbot)
tool_node = CustomToolNode(tools = tools)
graph_builder.add_node("tools", tool_node)

graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)

graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")
graph = graph_builder.compile(checkpointer=memory)

# pick a thread to use as the key for this conversation
config = {"configurable": {"thread_id": "1"}}



def stream_graph_updates(user_input: str):
    # 1) Send the user's original message into the graph
    initial_payload = {
        "messages": [
            { "role": "user", "content": user_input }
        ]
    }
    # Use stream_mode="values" so that we get each new Message object as it appears
    stream_iterator = graph.stream(initial_payload, config, stream_mode="values")

    for event in stream_iterator:
        # Get the messages list from the event
        messages = list(event.values())[-1]  # This is the messages list
        
        # Get the last message from the messages list
        if messages and len(messages) > 0:
            latest_message = messages[-1]  # This is the actual message object
            latest_message.pretty_print()

            # 2) If the LLM issued any tool_call, it will appear in latest_message.tool_calls (a list)
            if hasattr(latest_message, 'tool_calls') and latest_message.tool_calls:
                tool_call = latest_message.tool_calls[0]

                # 3) Only handle our human_assistance requests here
                if tool_call["name"] == "human_assistance":
                    # a) Show the exact query to the human
                    human_prompt = tool_call["args"]["query"]
                    human_reply = input(f"(assistant asks: {human_prompt})\nYou: ")

                    # b) Wrap the human's reply into a ToolMessage with the same tool_call.id
                    human_tool_msg = ToolMessage(
                        tool_call_id=tool_call["id"],  # Note: use tool_call_id, not tool
                        name="human_assistance",
                        content=human_reply
                    )

                    # 4) Resume the graph by streaming again, feeding in exactly that ToolMessage
                    resume_payload = { "messages": [human_tool_msg] }
                    resume_iterator = graph.stream(resume_payload, config, stream_mode="values")

                    # 5) Print out every new Message that the LLM emits after the human reply
                    for resume_event in resume_iterator:
                        resumed_messages = list(resume_event.values())[-1]
                        if resumed_messages and len(resumed_messages) > 0:
                            resumed_message = resumed_messages[-1]
                            resumed_message.pretty_print()

                    # Once done resuming, break out of the outer loop
                    break

while True:
    try:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            snapshot = graph.get_state(config)
            print(snapshot)
            print("Goodbye!")
            break
        stream_graph_updates(user_input)
    except:
        # fallback if input() is not available
        user_input = "What do you know about LangGraph?"
        print("User: " + user_input)
        stream_graph_updates(user_input)
        break
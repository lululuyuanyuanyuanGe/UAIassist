from typing_extensions import TypedDict, Annotated
from langchain_core.messages import AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

# Shared state schema used by parent and all subgraphs
class SharedState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    current_task: str
    metadata: dict

# Research Agent Subgraph
def research_step_1(state: SharedState):
    """Initial research gathering step"""
    new_message = {
        "role": "assistant",
        "content": f"Starting research for: {state['current_task']}"
    }
    return {
        "messages": [new_message],
        "metadata": {
            **state["metadata"],
            "research_started": True
        }
    }

def research_step_2(state: SharedState):
    """Research analysis step"""
    new_message = {
        "role": "assistant", 
        "content": "Research analysis completed with findings"
    }
    return {
        "messages": [new_message],
        "metadata": {
            **state["metadata"],
            "research_completed": True
        }
    }

# Build research subgraph
research_builder = StateGraph(SharedState)
research_builder.add_node("gather_info", research_step_1)
research_builder.add_node("analyze_info", research_step_2)
research_builder.add_edge(START, "gather_info")
research_builder.add_edge("gather_info", "analyze_info")
research_builder.add_edge("analyze_info", END)
research_subgraph = research_builder.compile()

# Writing Agent Subgraph
def writing_step_1(state: SharedState):
    """Draft creation step"""
    new_message = {
        "role": "assistant",
        "content": f"Creating draft for: {state['current_task']}"
    }
    return {
        "messages": [new_message],
        "metadata": {
            **state["metadata"],
            "draft_created": True
        }
    }

def writing_step_2(state: SharedState):
    """Content enhancement step"""
    new_message = {
        "role": "assistant",
        "content": "Enhanced draft with additional details and structure"
    }
    return {
        "messages": [new_message],
        "metadata": {
            **state["metadata"],
            "content_enhanced": True
        }
    }

# Build writing subgraph
writing_builder = StateGraph(SharedState)
writing_builder.add_node("create_draft", writing_step_1)
writing_builder.add_node("enhance_content", writing_step_2)
writing_builder.add_edge(START, "create_draft")
writing_builder.add_edge("create_draft", "enhance_content")
writing_builder.add_edge("enhance_content", END)
writing_subgraph = writing_builder.compile()

# Review Agent Subgraph
def review_step_1(state: SharedState):
    """Content review step"""
    new_message = {
        "role": "assistant",
        "content": "Reviewing content for quality and accuracy"
    }
    return {
        "messages": [new_message],
        "metadata": {
            **state["metadata"],
            "review_completed": True
        }
    }

def review_step_2(state: SharedState):
    """Final approval step"""
    new_message = {
        "role": "assistant",
        "content": f"Final approval for task: {state['current_task']}"
    }
    return {
        "messages": [new_message],
        "metadata": {
            **state["metadata"],
            "approved": True
        }
    }

# Build review subgraph
review_builder = StateGraph(SharedState)
review_builder.add_node("review_content", review_step_1)
review_builder.add_node("final_approval", review_step_2)
review_builder.add_edge(START, "review_content")
review_builder.add_edge("review_content", "final_approval")
review_builder.add_edge("final_approval", END)
review_subgraph = review_builder.compile()

# Parent Graph - Direct Integration of Subgraphs
def initialization_node(state: SharedState):
    """Initialize the workflow"""
    new_message = {
        "role": "assistant",
        "content": f"Initializing workflow for: {state['current_task']}"
    }
    return {
        "messages": [new_message],
        "metadata": {
            **state["metadata"],
            "workflow_started": True
        }
    }

def completion_node(state: SharedState):
    """Finalize the workflow"""
    new_message = {
        "role": "assistant",
        "content": "Workflow completed successfully"
    }
    return {
        "messages": [new_message],
        "metadata": {
            **state["metadata"],
            "workflow_completed": True
        }
    }

# Build parent graph with direct subgraph integration[2]
parent_builder = StateGraph(SharedState)
parent_builder.add_node("initialize", initialization_node)
parent_builder.add_node("research_agent", research_subgraph)  # Direct addition[2]
parent_builder.add_node("writing_agent", writing_subgraph)    # Direct addition[2]
parent_builder.add_node("review_agent", review_subgraph)      # Direct addition[2]
parent_builder.add_node("complete", completion_node)

# Create linear workflow
parent_builder.add_edge(START, "initialize")
parent_builder.add_edge("initialize", "research_agent")
parent_builder.add_edge("research_agent", "writing_agent")
parent_builder.add_edge("writing_agent", "review_agent")
parent_builder.add_edge("review_agent", "complete")
parent_builder.add_edge("complete", END)

# Compile the parent graph
multi_agent_workflow = parent_builder.compile()

# Example usage
if __name__ == "__main__":
    initial_state = {
        "messages": [
            {
                "role": "user",
                "content": "Create a comprehensive report on renewable energy"
            }
        ],
        "current_task": "renewable energy report",
        "metadata": {}
    }
    
    # Stream the workflow with subgraph outputs[2]
    for chunk in multi_agent_workflow.stream(
        initial_state, 
        subgraphs=True,  # Enable subgraph streaming[2]
        stream_mode="updates"
    ):
        print(f"Chunk: {chunk}")
    
    print("\n" + "="*50 + "\n")
    
    # Get final result
    final_result = multi_agent_workflow.invoke(initial_state)
    print("Final Messages:")
    for i, message in enumerate(final_result["messages"], 1):
        print(f"{i}. {message['role']}: {message['content']}")
    
    print(f"\nFinal Metadata: {final_result['metadata']}")

# This is an example of using subgraph to build our complex ai agent system

from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

# Define different state schemas for each subgraph
class ResearchAgentState(TypedDict):
    research_query: str
    research_results: list[str]
    confidence_score: float

class WritingAgentState(TypedDict):
    content_requirements: str
    research_data: list[str]
    draft_content: str
    word_count: int

class ReviewAgentState(TypedDict):
    content_to_review: str
    review_criteria: list[str]
    feedback: str
    approved: bool

# Parent graph state - completely different from subgraph states
class MainWorkflowState(TypedDict):
    user_request: str
    current_stage: str
    final_output: str
    metadata: dict

# Define the research subgraph
def research_node_1(state: ResearchAgentState):
    # Simulate research process
    query = state["research_query"]
    return {
        "research_results": [f"Research result 1 for: {query}", f"Research result 2 for: {query}"],
        "confidence_score": 0.85
    }

def research_node_2(state: ResearchAgentState):
    # Process and refine research results
    results = state["research_results"]
    confidence = state["confidence_score"]
    
    if confidence > 0.8:
        refined_results = [f"High-quality: {result}" for result in results]
    else:
        refined_results = [f"Needs verification: {result}" for result in results]
    
    return {"research_results": refined_results}

research_builder = StateGraph(ResearchAgentState)
research_builder.add_node("gather_data", research_node_1)
research_builder.add_node("refine_data", research_node_2)
research_builder.add_edge(START, "gather_data")
research_builder.add_edge("gather_data", "refine_data")
research_builder.add_edge("refine_data", END)
research_subgraph = research_builder.compile()

# Define the writing subgraph
def writing_node_1(state: WritingAgentState):
    # Create initial draft
    requirements = state["content_requirements"]
    data = state["research_data"]
    
    draft = f"Draft based on: {requirements}\nUsing data: {', '.join(data[:2])}"
    return {
        "draft_content": draft,
        "word_count": len(draft.split())
    }

def writing_node_2(state: WritingAgentState):
    # Enhance the draft
    draft = state["draft_content"]
    enhanced_draft = f"Enhanced: {draft}\nAdditional analysis and conclusions."
    
    return {
        "draft_content": enhanced_draft,
        "word_count": len(enhanced_draft.split())
    }

writing_builder = StateGraph(WritingAgentState)
writing_builder.add_node("create_draft", writing_node_1)
writing_builder.add_node("enhance_draft", writing_node_2)
writing_builder.add_edge(START, "create_draft")
writing_builder.add_edge("create_draft", "enhance_draft")
writing_builder.add_edge("enhance_draft", END)
writing_subgraph = writing_builder.compile()

# Define the review subgraph
def review_node_1(state: ReviewAgentState):
    # Perform initial review
    content = state["content_to_review"]
    criteria = state["content_to_review"]
    
    # Simulate review process
    feedback = f"Review feedback for content: {content[:50]}..."
    approved = len(content) > 100  # Simple approval logic
    
    return {
        "feedback": feedback,
        "approved": approved
    }

review_builder = StateGraph(ReviewAgentState)
review_builder.add_node("review_content", review_node_1)
review_builder.add_edge(START, "review_content")
review_builder.add_edge("review_content", END)
review_subgraph = review_builder.compile()

# Parent graph nodes that call subgraphs with state transformation
def call_research_agent(state: MainWorkflowState):
    """Transform parent state to research state, call subgraph, transform back"""[1]
    # Transform parent state to research subgraph state
    research_input = {
        "research_query": state["user_request"],
        "research_results": [],
        "confidence_score": 0.0
    }
    
    # Invoke the research subgraph
    research_output = research_subgraph.invoke(research_input)[1]
    
    # Transform research output back to parent state
    return {
        "current_stage": "research_complete",
        "metadata": {
            "research_results": research_output["research_results"],
            "confidence": research_output["confidence_score"]
        }
    }

def call_writing_agent(state: MainWorkflowState):
    """Transform parent state to writing state, call subgraph, transform back"""[1]
    # Extract research results from metadata
    research_data = state["metadata"].get("research_results", [])
    
    # Transform parent state to writing subgraph state
    writing_input = {
        "content_requirements": state["user_request"],
        "research_data": research_data,
        "draft_content": "",
        "word_count": 0
    }
    
    # Invoke the writing subgraph
    writing_output = writing_subgraph.invoke(writing_input)[1]
    
    # Transform writing output back to parent state
    return {
        "current_stage": "writing_complete",
        "metadata": {
            **state["metadata"],
            "draft_content": writing_output["draft_content"],
            "word_count": writing_output["word_count"]
        }
    }

def call_review_agent(state: MainWorkflowState):
    """Transform parent state to review state, call subgraph, transform back"""[1]
    # Extract draft content from metadata
    draft_content = state["metadata"].get("draft_content", "")
    
    # Transform parent state to review subgraph state
    review_input = {
        "content_to_review": draft_content,
        "review_criteria": ["clarity", "accuracy", "completeness"],
        "feedback": "",
        "approved": False
    }
    
    # Invoke the review subgraph
    review_output = review_subgraph.invoke(review_input)[1]
    
    # Transform review output back to parent state
    final_output = draft_content if review_output["approved"] else f"NEEDS REVISION: {draft_content}"
    
    return {
        "current_stage": "review_complete",
        "final_output": final_output,
        "metadata": {
            **state["metadata"],
            "review_feedback": review_output["feedback"],
            "approved": review_output["approved"]
        }
    }

# Build the parent graph
parent_builder = StateGraph(MainWorkflowState)
parent_builder.add_node("research_agent", call_research_agent)
parent_builder.add_node("writing_agent", call_writing_agent)
parent_builder.add_node("review_agent", call_review_agent)

# Create linear workflow
parent_builder.add_edge(START, "research_agent")
parent_builder.add_edge("research_agent", "writing_agent")
parent_builder.add_edge("writing_agent", "review_agent")
parent_builder.add_edge("review_agent", END)

# Compile the parent graph
multi_agent_workflow = parent_builder.compile()

# Example usage
if __name__ == "__main__":
    initial_state = {
        "user_request": "Create a report on renewable energy trends",
        "current_stage": "starting",
        "final_output": "",
        "metadata": {}
    }
    
    # Execute the workflow
    for chunk in multi_agent_workflow.stream(initial_state, subgraphs=True):
        print(f"Chunk: {chunk}")
    
    # Get final result
    final_result = multi_agent_workflow.invoke(initial_state)
    print(f"\nFinal Result: {final_result}")

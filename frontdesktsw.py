from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
import uuid
import json

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# 定义前台接待员状态
class frontDesakRequirementState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    table_header: list[str]
    requirements_complete: bool
    generated_template: Optional[str]
    next_action: Optional[str]
    has_template: bool
    excel_form_type: Optional[str]
    collected_requirements: Dict[str, Any]

@tool
def save_requirements(requirements: Dict[str, Any]) -> str:
    """Save collected requirements for later workflow"""
    # In a real implementation, this would save to a database
    timestamp = datetime.now().isoformat()
    saved_data = {
        "timestamp": timestamp,
        "requirements": requirements
    }
    # For now, just return confirmation
    return f"Requirements saved successfully at {timestamp}"

class FrontDeskAgent:
    """
    基于LangGraph的AI代理系统，用于判断用户是否给出了表格生成模板
    """

    def __init__(self, model_name: str = "gpt-4o", checkpoint_path: str = "checkpoints.db"):
        self.model_name = model_name
        self.llm = ChatOpenAI(model=model_name, temperature=0.1)
        self.memory = MemorySaver()
        self.tools = [save_requirements]
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph for AI-driven requirement gathering"""
        workflow = StateGraph(frontDesakRequirementState)
        
        # Add nodes
        workflow.add_node("check_template", self._check_template_node)
        workflow.add_node("determine_form_type", self._determine_form_type_node)
        workflow.add_node("gather_requirements", self._gather_requirements_node)
        workflow.add_node("store_information", self._store_information_node)
        workflow.add_node("template_provided", self._template_provided_node)
        
        # Set entry point
        workflow.set_entry_point("check_template")
        
        # Add edges
        workflow.add_conditional_edges(
            "check_template",
            self._route_after_template_check,
            {
                "has_template": "template_provided",
                "no_template": "determine_form_type"
            }
        )
        
        workflow.add_edge("template_provided", END)
        workflow.add_edge("determine_form_type", "gather_requirements")
        workflow.add_conditional_edges(
            "gather_requirements",
            self._route_after_requirements,
            {
                "complete": "store_information",
                "continue": "gather_requirements"
            }
        )
        workflow.add_edge("store_information", END)
        
        return workflow.compile(checkpointer=self.memory)

    def _check_template_node(self, state: frontDesakRequirementState) -> frontDesakRequirementState:
        """检查用户输入是否包含表格模板"""
        template_check_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a front desk agent analyzing user input to determine if they have provided an Excel template or form structure.

            Look for:
            - Column headers or field names
            - Table structure descriptions
            - Specific data fields mentioned
            - Any organized layout information

            Respond with 'YES' if a template/structure is provided, 'NO' if not.
            """),
            ("human", "{user_input}")
        ])
        
        latest_message = state["messages"][-1].content if state["messages"] else ""
        
        response = self.llm.invoke(
            template_check_prompt.invoke(user_input=latest_message)
        )
        
        has_template = "YES" in response.content.upper()
        
        return {
            **state,
            "has_template": has_template,
            "messages": state["messages"] + [AIMessage(content=f"Template analysis: {'Found' if has_template else 'Not found'}")],
        }

    def _template_provided_node(self, state: frontDesakRequirementState) -> frontDesakRequirementState:
        """处理用户已提供模板的情况"""
        response_message = AIMessage(content="Great! I can see you've provided a template structure. I'll use this to create your Excel form.")
        
        return {
            **state,
            "messages": state["messages"] + [response_message],
            "requirements_complete": True,
            "next_action": "create_excel_from_template"
        }

    def _determine_form_type_node(self, state: frontDesakRequirementState) -> frontDesakRequirementState:
        """确定Excel表格类型"""
        form_type_prompt = ChatPromptTemplate.from_messages([
            ("system", """Based on the user's request, determine what type of Excel form they need. 
            
            Common types include:
            - Data collection form (surveys, feedback)
            - Inventory tracking
            - Contact list
            - Financial tracking
            - Project management
            - Employee records
            - Event planning
            - Other (specify)
            
            Provide a brief analysis and suggest the most appropriate form type."""),
            ("human", "{user_input}")
        ])
        
        latest_message = state["messages"][-1].content if state["messages"] else ""
        
        response = self.llm.invoke(
            form_type_prompt.format_messages(user_input=latest_message)
        )
        
        return {
            **state,
            "excel_form_type": response.content,
            "messages": state["messages"] + [response],
        }

    def _gather_requirements_node(self, state: frontDesakRequirementState) -> frontDesakRequirementState:
        """收集用户需求信息"""
        requirements_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are gathering detailed requirements for creating an Excel form. 
            
            Based on the form type identified, ask specific questions about:
            - What columns/fields are needed
            - Data types for each field
            - Any validation rules
            - Formatting preferences
            - Number of expected rows
            - Any calculations needed
            
            Ask one clear, specific question at a time. Be conversational and helpful."""),
            ("human", "Form type: {form_type}\n\nUser input: {user_input}")
        ])
        
        latest_message = state["messages"][-1].content if state["messages"] else ""
        form_type = state.get("excel_form_type", "General form")
        
        response = self.llm.invoke(
            requirements_prompt.format_messages(
                form_type=form_type,
                user_input=latest_message
            )
        )
        
        # Simple logic to determine if we have enough information
        # In a real implementation, this would be more sophisticated
        collected_reqs = state.get("collected_requirements", {})
        collected_reqs["latest_response"] = latest_message
        
        return {
            **state,
            "collected_requirements": collected_reqs,
            "messages": state["messages"] + [response],
        }

    def _store_information_node(self, state: frontDesakRequirementState) -> frontDesakRequirementState:
        """存储收集到的信息"""
        # Use the tool to save requirements
        requirements_data = {
            "form_type": state.get("excel_form_type"),
            "requirements": state.get("collected_requirements", {}),
            "session_id": state.get("session_id"),
            "has_template": state.get("has_template", False)
        }
        
        result = save_requirements(requirements_data)
        
        confirmation_message = AIMessage(
            content="Perfect! I've collected all the necessary information for your Excel form. "
                   "Your requirements have been stored and will be used to create your customized Excel template. "
                   "The next step will be generating the actual Excel file based on your specifications."
        )
        
        return {
            **state,
            "requirements_complete": True,
            "messages": state["messages"] + [confirmation_message],
            "next_action": "create_excel_form"
        }

    def _route_after_template_check(self, state: frontDesakRequirementState) -> str:
        """路由决策：模板检查后的下一步"""
        return "has_template" if state["has_template"] else "no_template"

    def _route_after_requirements(self, state: frontDesakRequirementState) -> str:
        """路由决策：需求收集后的下一步"""
        # Simple logic - in real implementation, this would check if we have sufficient information
        collected_reqs = state.get("collected_requirements", {})
        
        # For demo purposes, assume complete after a few interactions
        message_count = len([msg for msg in state["messages"] if isinstance(msg, HumanMessage)])
        
        if message_count > 3:  # After a few back-and-forth interactions
            return "complete"
        else:
            return "continue"

    def process_user_input(self, user_input: str, session_id: str = None) -> Dict[str, Any]:
        """处理用户输入的主方法"""
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "session_id": session_id,
            "table_header": [],
            "requirements_complete": False,
            "generated_template": None,
            "next_action": None,
            "has_template": False,
            "excel_form_type": None,
            "collected_requirements": {}
        }
        
        config = {"configurable": {"thread_id": session_id}}
        result = self.graph.invoke(initial_state, config)
        
        return {
            "response": result["messages"][-1].content if result["messages"] else "No response generated",
            "session_id": session_id,
            "next_action": result.get("next_action"),
            "requirements_complete": result.get("requirements_complete", False),
            "has_template": result.get("has_template", False)
        }

# Initialize the agent
agent = FrontDeskAgent()

# Process user input
result = agent.process_user_input("I need to create an inventory tracking sheet")

# The agent will:
# 1. Check if template provided (no)
# 2. Determine it's an inventory form
# 3. Ask questions about inventory fields
# 4. Store requirements when complete
        


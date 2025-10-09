import logging
from typing import AsyncGenerator, Dict, Any
import os

# Import ADK components
from google.adk.agents import LlmAgent, BaseAgent
from google.adk.events import Event
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools import ToolContext, google_search
from google.adk.tools.agent_tool import AgentTool
from typing_extensions import override
from dotenv import load_dotenv

# Import our new memory tools

load_dotenv()



# --- 1. Define the Session-based Memory Tools ---
# These tools interact with the session service managed by ADK.
# No more manual sqlite3 connections!

def save_user_preferences(tool_context: ToolContext, new_preferences: Dict[str, Any]) -> str:
    """
    Saves or updates user preferences in the persistent session storage.
    It merges new preferences with any existing ones.

    Args:
        new_preferences: A dictionary of new preferences to save. 
                         Example: {"cuisine": "Italian", "interests": ["modern art"]}
    """
    # Get existing preferences from the session, default to an empty dict if none exist.
    # 'user_preferences' is the key we use to store the data in the session.
    current_preferences = tool_context.session.get_data('user_preferences') or {}
    
    # Update the current preferences with the new ones
    current_preferences.update(new_preferences)
    
    # Save the updated dictionary back to the session.
    # ADK's DbSessionService handles the database write.
    tool_context.session.set_data('user_preferences', current_preferences)
    
    return f"Preferences updated successfully: {new_preferences}"

def recall_user_preferences(tool_context: ToolContext) -> Dict[str, Any]:
    """Recalls all saved preferences for the current user from the session."""
    # Retrieve the data associated with the key 'user_preferences'.
    # ADK's DbSessionService handles the database read for the current user.
    preferences = tool_context.session.get_data('user_preferences')
    
    if preferences:
        return preferences
    else:
        return {"message": "No preferences found for this user."}


# --- 2. Define the Specialist "Tool" Agent ---
# This agent remains unchanged.
planner_tool_agent = LlmAgent(
    name="PlannerToolAgent",
    model="gemini-2.5-flash", # Note: Updated to a generally available model name
    description="A specialist that finds activities and restaurants based on a user's request and preferences.",
    instruction="""
    You are a planning assistant. Based on the user's request and their provided preferences, find one activity and one restaurant in Sunnyvale.
    Output the plan as a simple JSON object.
    Example: {"activity": "The Tech Interactive", "restaurant": "Il Postale"}
    """,
    tools=[google_search]
)



# --- 3. Define the Main Coordinator Agent ---
# This agent is updated to use the new session-based tools and instructions.
root_agent = LlmAgent(
    name="MemoryCoordinatorAgent",
    model="gemini-2.5-pro", # Note: Updated to a generally available model name
    instruction="""
    You are a highly intelligent, personalized trip planner with a persistent memory.
    You must follow a strict sequence of actions to provide a personalized experience.

    --- Your Internal Workflow ---

    1.  **RECALL FIRST:** At the absolute beginning of the conversation, your first action MUST be to call the `recall_user_preferences` tool to see if you've spoken to this user before.

    2.  **PERSONALIZE & PLAN:**
        - Use the recalled preferences to enrich the user's current request.
        - Call the `PlannerToolAgent` with the combined request (e.g., "The user wants a museum, and their preference is for modern art"). This tool will do the web search and return a plan.

    3.  **PRESENT & LEARN:** Present the plan returned by the `PlannerToolAgent`. Then, explicitly ask for feedback and if there are any new preferences you should save for next time.

    4.  **SAVE LAST:** If the user provides new preferences to remember, your final action MUST be to call the `save_user_preferences` tool. You must pass the new information as a dictionary. For example, if the user says they like spicy food, call the tool with `{"cuisine": "spicy"}`.
    """,
    # --- UPDATED: The tools list now uses our new session-based functions ---
    tools=[
        recall_user_preferences,
        save_user_preferences,
        AgentTool(agent=planner_tool_agent)
    ]
)

print("🤖 Memory Coordinator Agent (with ADK Session Service) is ready.")
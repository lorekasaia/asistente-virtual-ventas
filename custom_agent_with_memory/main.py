import asyncio
import os
from pathlib import Path

# Import ADK components
from google.adk.runners import Runner
# --- THIS LINE HAS CHANGED ---
from google.adk.services.session_service import DbSessionService 
from google.genai.types import Content, Part

# Import the root_agent from your agent.py file
from agent import root_agent

# --- 1. Configuration for Persistent Storage ---
# We'll store the session database in a hidden ADK directory in your home folder.
SESSIONS_DIR = Path(os.path.expanduser("~")) / ".adk" / "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True) # Ensure the directory exists

DB_FILE = SESSIONS_DIR / "adk_cli_sessions.db"
SESSION_URI = f"sqlite:///{DB_FILE}"

# Define a unique identifier for the user interacting with the CLI.
MY_USER_ID = "local_cli_user_001"


async def main():
    """
    Sets up the DbSessionService and Runner to start an interactive chat loop.
    """
    print("🤖 Initializing Personalized Trip Planner CLI...")
    print(f"🗄️  Session database is at: {DB_FILE}")
    print("--------------------------------------------------")
    print("Try saying: 'Find a fun activity for me.'")
    print("Then try: 'Remember that I like modern art.'")
    print("Type 'quit' or 'exit' to end the session.")
    print("--------------------------------------------------")

    # --- 2. Initialize the Persistent Session Service ---
    # This service will read from and write to the SQLite database file.
    session_service = DbSessionService(db_uri=SESSION_URI)

    # --- 3. Get or Create a Session ---
    # This will resume the last session for MY_USER_ID or start a new one.
    # This is how the agent remembers things between script runs.
    session = await session_service.get_or_create_session(
        app_name=root_agent.name,
        user_id=MY_USER_ID
    )
    print(f"✅ Session '{session.id}' is ready for user '{session.user_id}'.")

    # --- 4. Initialize the Runner ---
    # The Runner connects the agent logic with the session management.
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name=root_agent.name
    )

    # --- 5. Interactive Chat Loop ---
    while True:
        try:
            query = input("You: ")
            if query.lower() in ["quit", "exit"]:
                print("🤖 Goodbye!")
                break

            print("Agent: ", end="", flush=True)

            # Use the runner to execute the query for the specific user and session.
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=Content(parts=[Part(text=query)], role="user")
            ):
                # Stream the LLM response chunks for a better user experience
                if event.is_llm_response_chunk():
                    print(event.content.parts[0].text, end="", flush=True)

            print("\n") # Add a newline after the agent's full response

        except (KeyboardInterrupt, EOFError):
            print("\n🤖 Goodbye!")
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Shutting down.")
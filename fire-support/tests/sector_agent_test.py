import sys
import os
import json
import logging
from pathlib import Path

# Add the project root to sys.path to allow imports from 'llm' package
# This assumes the script is run from fire-support/tests/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from llm.llm_client import LLMClient
    logger_initialized = True
except ImportError as e:
    print(f"Error: Could not import LLMClient. Make sure you are running from the correct directory. {e}")
    logger_initialized = False

def run_sector_agent_test():
    # Setup logging to see the LLM communication details
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    if not logger_initialized:
        return

    # 1. Initialize LLM Client
    # It will automatically try to load OPENAI_API_KEY from .env or .local.env in fire-support/
    # You can also pass api_key="your-key-here" directly to LLMClient()
    api_key = os.environ.get("OPENAI_API_KEY")
    
    logger.info("Initializing LLM Client for Sector Agent test...")
    client = LLMClient(api_key=api_key)
    
    if client.use_mock:
        logger.warning("OPENAI_API_KEY not found in environment or .env files. Running in MOCK mode.")
        logger.warning("To use a real LLM, please set OPENAI_API_KEY.")
    else:
        logger.info(f"LLM Client initialized with model: {client.model}")

    # 2. Mock data representing a Sector Agent (Fire Brigade) situation
    agent_id = "sector_brigade_alpha"
    
    # Current status of our agent
    current_state = {
        "agent_id": agent_id,
        "type": "fire_brigade",
        "status": "AVAILABLE",
        "location": {"latitude": 52.2297, "longitude": 21.0122},
        "water_reserve": 100,
        "current_sector_id": 5
    }
    
    # Available sectors that need attention
    available_sectors = [
        {
            "sector_id": 10,
            "name": "Dry Pine Forest",
            "fire_level": 82.5,
            "burn_level": 20.0,
            "distance_from_agent": 1.5,
            "priority": "CRITICAL"
        },
        {
            "sector_id": 15,
            "name": "Grassland Buffer",
            "fire_level": 15.0,
            "burn_level": 2.0,
            "distance_from_agent": 0.8,
            "priority": "LOW"
        }
    ]
    
    # What other agents are doing (context for coordination)
    peer_actions = [
        {
            "agent_id": "brigade_beta",
            "action": "move_to",
            "target_sector_id": 10,
            "reasoning": "Large fire detected, proceeding to contain northern edge."
        }
    ]

    print(f"\n" + "="*60)
    print(f" PROMPT EXECUTION: AGENT {agent_id}")
    print("="*60 + "\n")
    
    # 3. Perform the decision-making prompt
    # This uses the 'make_decision_system.txt' and 'make_decision_user.txt' prompts
    decision = client.make_decision(
        agent_id=agent_id,
        current_state=current_state,
        available_sectors=available_sectors,
        peer_actions=peer_actions
    )

    # 4. Show the results
    print("\n" + "-"*30)
    print("AGENT DECISION RESULT:")
    print("-"*30)
    print(json.dumps(decision, indent=4))
    print("-"*30 + "\n")

    if not client.use_mock:
        print("  SUCCESS: Real LLM call completed.")
    else:
        print("ℹ INFO: Mock response generated (no API key).")

if __name__ == "__main__":
    run_sector_agent_test()

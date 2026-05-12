import os
import json
import logging
import re
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List            
import openai

logger = logging.getLogger(__name__)

class LLMClient:
    """
    LLM Client for fire simulation agents.
    """
    
    def __init__(self, model=None, api_key=None, base_url=None):
        _fire_support_root = Path(__file__).parent.parent
        _env_path = _fire_support_root / ".env"
        _local_env_path = _fire_support_root / ".local.env"
        
        if _env_path.exists():
            load_dotenv(_env_path)
            logger.debug(f"[LLM-Client] Loaded .env from: {_env_path}")
        elif _local_env_path.exists():
            load_dotenv(_local_env_path)
            logger.debug(f"[LLM-Client] Loaded .local.env from: {_local_env_path}")
        else:
            load_dotenv() 
            logger.debug(f"[LLM-Client] Neither .env nor .local.env found at {_fire_support_root}, using default")

        self.model    = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.api_key  = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_API_BASE")
        self._prompt_cache = {}
        self._prompts_dir = Path(__file__).parent / "prompts"
        
        logger.debug("=" * 80)
        logger.debug("[LLM-CLIENT] INITIALIZATION")
        logger.debug("=" * 80)
        logger.debug(f"Model: {self.model}")
        logger.debug(f"API Key: {'SET' if self.api_key else 'NOT SET'}")
        logger.debug(f"Base URL: {self.base_url or 'default (OpenAI)'}")
        logger.debug("=" * 80)
    
    def _load_prompt(self, filename: str) -> str:
        """Load a prompt from a text file, with caching."""
        if filename in self._prompt_cache:
            return self._prompt_cache[filename]
        
        prompt_path = self._prompts_dir / filename
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                self._prompt_cache[filename] = content
                return content
        except FileNotFoundError:
            logger.error(f"Prompt file not found: {prompt_path}")
            return ""
        except Exception as e:
            logger.error(f"Error loading prompt file {prompt_path}: {e}")
            return ""

    def complete(self, prompt: str, system_prompt: str = "You are an intelligent fire brigade coordinator assistant.") -> str:
        """
        Perform a synchronous completion call.
        
        IMPORTANT:
        - If no API key is configured or OpenAI client fails, this returns an empty string
          and logs the error. No mock / fake content is generated.
        """
        if not self.api_key:
            logger.error("[LLM-CLIENT] OPENAI_API_KEY is not configured; cannot call LLM")
            return ""
        
        try:            
            try:
                if self.base_url:
                    client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
                else:
                    client = openai.OpenAI(api_key=self.api_key)
            except TypeError as te:
                logger.warning(f"Could not initialize OpenAI with base_url: {te}. Retrying without it.")
                client = openai.OpenAI(api_key=self.api_key)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content
        
        except ImportError:
            logger.error("openai package not installed; cannot call LLM")
            return ""
        
        except Exception as e:
            logger.error(f"OpenAI chat.completions.create failed: {e}", exc_info=True)
            return ""

    def make_decision(
        self, 
        agent_id: str,
        current_state: Dict[str, Any],
        available_sectors: List[Dict[str, Any]],
        peer_actions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Ask LLM to make a decision for a fire brigade agent.
        
        Args:
            agent_id: ID of the agent
            current_state: Current state of the agent (location, state, etc.)
            available_sectors: List of sectors with fires that need attention
            peer_actions: List of actions taken by other brigades
            
        Returns:
            Decision dict with 'decision', 'reasoning', 'priority', and optional 'target_sector_id'
        """
        system_prompt = self._load_prompt("make_decision_system.txt")
        if not system_prompt:
            system_prompt = "You are an intelligent fire brigade coordinator assistant."
        
        prompt_template = self._load_prompt("make_decision_user.txt")
        if not prompt_template:
            prompt = f"""
                * Fire Brigade {agent_id} Decision Request:
                * Current State: {json.dumps(current_state, indent=2)}
                * Available Sectors with Fires: {json.dumps(available_sectors, indent=2)}
                * Recent Peer Actions (other brigades): {json.dumps(peer_actions, indent=2)}
                * What should this fire brigade do? Return JSON decision."""
        else:
            prompt = prompt_template.format(
                agent_id          = agent_id,
                current_state     = json.dumps(current_state, indent=2),
                available_sectors = json.dumps(available_sectors, indent=2),
                peer_actions      = json.dumps(peer_actions, indent=2)
            )
        
        response = self.complete(prompt, system_prompt)
        
        try:
            decision_dict = None
            if response.strip().startswith("{"):
                decision_dict = json.loads(response.strip())
            elif "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                decision_dict = json.loads(response[start:end])
            
            if decision_dict:
                decision_type = decision_dict.get("decision", "").lower()
                if decision_type in ("move_to", "extinguish") and "target_sector_id" not in decision_dict:
                    if available_sectors:
                        best_sector = max(available_sectors, key=lambda s: s.get("fire_level", 0))
                        decision_dict["target_sector_id"] = best_sector.get("sector_id")
                        logger.debug(f"[LLM] Extracted target_sector_id {decision_dict['target_sector_id']} from available sectors")
                
                return decision_dict
            
            logger.warning(f"LLM response does not contain JSON: {response[:100]}")
            if available_sectors:
                best_sector = max(available_sectors, key=lambda s: s.get("fire_level", 0))
                return {
                    "decision": "move_to",
                    "reasoning": f"LLM returned non-JSON response, using highest priority sector",
                    "priority": "MEDIUM",
                    "target_sector_id": best_sector.get("sector_id")
                }
            return {
                "decision": "stay_idle",
                "reasoning": f"LLM returned non-JSON response: {response[:50]}",
                "priority": "LOW"
            }
        except json.JSONDecodeError as e:
            pass
        except Exception as e:
            pass

    def analyze_peer_actions(
        self,
        agent_id: str,
        my_state: Dict[str, Any],
        peer_actions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze actions of other brigades and suggest adjustments.
        
        Args:
            agent_id: ID of the agent
            my_state: Current state of this agent
            peer_actions: List of actions taken by other brigades
            
        Returns:
            Analysis dict with 'adjustment', 'reasoning', 'new_target' (optional)
        """
        system_prompt = self._load_prompt("analyze_peer_actions_system.txt")

        if not system_prompt:
            system_prompt = """
                You are an intelligent fire brigade coordinator analyzing peer actions.
                When other brigades commit to fires, you should:
                - Avoid going to the same sector if it's already covered
                - Find alternative fires to extinguish
                - Coordinate efficiently
                - Adjust your plan if a better opportunity appears

                Return JSON with:
                - adjustment: "none" | "change_target" | "abort_current" | "wait"
                - reasoning: explanation
                - new_target_sector_id: (optional) if changing target
                """
        
        prompt_template = self._load_prompt("analyze_peer_actions_user.txt")
        if not prompt_template:
            prompt = f"""
                Fire Brigade {agent_id} Peer Analysis:
                My Current State: {json.dumps(my_state, indent=2)}
                Recent Peer Actions: {json.dumps(peer_actions, indent=2)}
                Should I adjust my current plan based on peer actions? Return JSON analysis.
                """
        else:
            prompt = prompt_template.format(
                agent_id     = agent_id,
                my_state     = json.dumps(my_state, indent=2),
                peer_actions = json.dumps(peer_actions, indent=2)
            )
        
        response = self.complete(prompt, system_prompt)
        
        try:
            if response.strip().startswith("{"):
                return json.loads(response.strip())
            
            if "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                return json.loads(response[start:end])
            
            return {
                "adjustment": "none",
                "reasoning": f"LLM returned non-JSON: {response[:50]}"
            }
        except json.JSONDecodeError as e:
            return {}
        except Exception as e:
            return {}
    
    def evaluate_proposition(
        self,
        agent_id: str,
        proposition: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Evaluate a strategic proposition from an agent and provide coordinator feedback.
        
        Args:
            agent_id: ID of the agent making the proposition
            proposition: The proposition text from the agent
            context: Optional context about current situation
            
        Returns:
            Coordinator response text
        """
        system_prompt = self._load_prompt("evaluate_proposition_system.txt")
        if not system_prompt:
            system_prompt = """
                You are the Strategic Fire Coordinator overseeing fire brigades.
                IMPORTANT: 
                - Always explain your decision reasoning
                - Reference specific sectors when responding
                - Provide tactical guidance, not just approval/denial
                - Be supportive of good proposals, challenging of weak ones
                - Keep response under 25 words but be detailed"""
                        
        context_str = json.dumps(context, indent=2) if context else "No additional context"
        prompt_template = self._load_prompt("evaluate_proposition_user.txt")
        if not prompt_template:
            prompt = f"""
                Agent {agent_id} proposes: "{proposition}"
                Current Context: {context_str}
                Evaluate this proposal:
                1. Is it strategically sound?
                2. What are the implications?
                3. Should you approve, modify, or deny?
                Respond with a detailed tactical decision that explains reasoning."""
        else:
            prompt = prompt_template.format(
                agent_id    = agent_id,
                proposition = proposition,
                context     = context_str
            )
        
        return self.complete(prompt, system_prompt)
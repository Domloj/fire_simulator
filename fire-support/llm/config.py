"""
Configuration for LLM and recommendation modes.

Controls whether the system uses LLM-driven or heuristic-driven recommendations.
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum
from dotenv import load_dotenv

_fire_support_root = Path(__file__).parent.parent
_env_path = _fire_support_root / ".env"
_local_env_path = _fire_support_root / ".local.env"

env_loaded = False
if _env_path.exists():
    load_dotenv(_env_path)
    logger = logging.getLogger(__name__)
    logger.info(f"[CONFIG] Loaded .env from: {_env_path}")
    env_loaded = True
elif _local_env_path.exists():
    load_dotenv(_local_env_path)
    logger = logging.getLogger(__name__)
    logger.info(f"[CONFIG] Loaded .local.env from: {_local_env_path}")
    env_loaded = True
else:
    load_dotenv()
    logger = logging.getLogger(__name__)
    logger.warning(f"[CONFIG] Neither .env nor .local.env found at {_fire_support_root}, using default load_dotenv()")

class RecommendationMode(str, Enum):
    """Recommendation generation modes"""
    HEURISTIC = "heuristic"
    LLM = "llm"
    HYBRID = "hybrid"
    AUTO = "auto"

class AgentDecisionMode(str, Enum):
    """Agent decision-making modes"""
    HEURISTIC = "heuristic" 
    LLM = "llm" 
    HYBRID = "hybrid"  


class LLMConfig:
    """Configuration for LLM and recommendation system"""
    
    def __init__(
        self,
        llm_model: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None
    ):
        # Check LLM_ENABLED first - if false, disable everything
        llm_enabled_env = os.getenv("LLM_ENABLED", "true").lower()
        llm_globally_enabled = llm_enabled_env in ("true", "1", "yes")
        
        enable_llm_coord_env = os.getenv("ENABLE_LLM_COORDINATION", "true").lower()
        self.enable_llm_coordination = enable_llm_coord_env in ("true", "1", "yes") if llm_globally_enabled else False

        enable_agent_comm_env = os.getenv("ENABLE_AGENT_COMMUNICATION", "true").lower()
        self.enable_agent_communication = enable_agent_comm_env in ("true", "1", "yes") if llm_globally_enabled else False
        
        # If LLM coordination is disabled, force heuristic mode
        raw_recommendation_mode = os.getenv("RECOMMENDATION_MODE", "llm").lower()
        if not self.enable_llm_coordination and raw_recommendation_mode == "llm":
            logger.info("[CONFIG] RECOMMENDATION_MODE=llm but ENABLE_LLM_COORDINATION=false, forcing heuristic mode")
            self.recommendation_mode = "heuristic"
        else:
            self.recommendation_mode = raw_recommendation_mode
        
        self.agent_decision_mode = os.getenv(
            "AGENT_DECISION_MODE", "llm" 
        ).lower()
        
        # If agent communication is disabled, force heuristic agent decision mode
        if not self.enable_agent_communication and self.agent_decision_mode == "llm":
            logger.info("[CONFIG] AGENT_DECISION_MODE=llm but ENABLE_AGENT_COMMUNICATION=false, forcing heuristic mode")
            self.agent_decision_mode = "heuristic"

        self.llm_model          = llm_model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.llm_api_key        = llm_api_key or os.getenv("OPENAI_API_KEY") 
        self.llm_base_url       = llm_base_url or os.getenv("OPENAI_API_BASE")
        self.enable_agent_chat  = os.getenv("ENABLE_AGENT_LLM_CHAT", "true").lower() in ("true", "1", "yes")
        self.agent_llm_cooldown = int(os.getenv("AGENT_LLM_COOLDOWN_SECONDS", "30"))
        
        try:
            RecommendationMode(self.recommendation_mode)
        except ValueError:
            logger.warning(f"Invalid recommendation_mode: {self.recommendation_mode}, using 'hybrid'")
            self.recommendation_mode = "hybrid"
        
        try:
            AgentDecisionMode(self.agent_decision_mode)
        except ValueError:
            logger.warning(f"Invalid agent_decision_mode: {self.agent_decision_mode}, using 'hybrid'")
            self.agent_decision_mode = "hybrid"
    
    @property
    def use_llm_coordination(self) -> bool:
        """Whether to use LLM coordination in recommendations"""
        # enable_llm_coordination is already a bool after my fix
        if isinstance(self.enable_llm_coordination, bool):
            return self.enable_llm_coordination
        # Fallback for old format (string)
        return self.enable_llm_coordination in ("true", "1", "yes")
    
    @property
    def use_agent_llm(self) -> bool:
        """Whether agents should use LLM for decisions"""
        # enable_agent_communication is already a bool after my fix
        if isinstance(self.enable_agent_communication, bool):
            return self.enable_agent_communication
        # Fallback for old format (string)
        return self.enable_agent_communication in ("true", "1", "yes")
    
    @property
    def is_llm_enabled(self) -> bool:
        """Whether LLM is enabled in any capacity"""
        return self.use_llm_coordination
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return {
            "recommendation_mode": self.recommendation_mode,
            "agent_decision_mode": self.agent_decision_mode,
            "enable_llm_coordination": self.enable_llm_coordination,
            "enable_agent_communication": self.enable_agent_communication,
            "use_llm_coordination": self.use_llm_coordination,
            "use_agent_llm": self.use_agent_llm,
            "llm_model": self.llm_model,
            "llm_api_key_configured": bool(self.llm_api_key),
            "llm_base_url": self.llm_base_url
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'LLMConfig':
        """Create config from dictionary"""
        return cls(
            recommendation_mode=config_dict.get("recommendation_mode"),
            agent_decision_mode=config_dict.get("agent_decision_mode"),
            enable_llm_coordination=config_dict.get("enable_llm_coordination"),
            enable_agent_communication=config_dict.get("enable_agent_communication"),
            llm_model=config_dict.get("llm_model"),
            llm_api_key=config_dict.get("llm_api_key"),
            llm_base_url=config_dict.get("llm_base_url")
        )
    
    def __repr__(self) -> str:
        return (f"LLMConfig("
                f"recommendation_mode={self.recommendation_mode}, "
                f"agent_decision_mode={self.agent_decision_mode}, "
                f"llm_coordination={self.use_llm_coordination}, "
                f"agent_llm={self.use_agent_llm})")


_default_config: Optional[LLMConfig] = None


def get_config() -> LLMConfig:
    """Get global LLM configuration"""
    global _default_config
    if _default_config is None:
        _default_config = LLMConfig()
        logger.info(f"[CONFIG] LLM enabled: {_default_config.is_llm_enabled}")
    return _default_config


def set_config(config: LLMConfig):
    """Set global LLM configuration"""
    global _default_config
    _default_config = config
    logger.info(f"LLM configuration updated: {config}")

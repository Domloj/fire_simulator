from enum import Enum

class TopicRegistry(str, Enum):
    """
    Topic registry for fire-support agent communication.
    Uses same routing keys as backend for consistency.
    """
    # Agent communication - consumed by backend
    AGENT_ANNOUNCEMENTS = "simulation.agents.announcements"
    
    # LLM Agent Chat/Coordination
    LLM_AGENT_REQUESTS = "support.llm.requests"    # Agents announcing tasks
    LLM_AGENT_RESPONSES = "support.llm.responses"  # LLM strategic responses
    LLM_AGENT_PROPOSITIONS = "support.llm.propositions"
    LLM_AGENT_PROPOSITIONS_RESPONSES = "support.llm.propositions.responses"
    
    # Support system topics
    SUPPORT_RECOMMENDATIONS = "support.recommendations"
    SUPPORT_AGGREGATED_DATA = "support.data.aggregated"
    
    # Legacy - not used, kept for compatibility
    # AGENT_COMMUNICATION = "simulation.agents.communication"
"""
Agent Factory
Creates and manages different types of agents
"""
from typing import Dict, Optional
from .base_agent import BaseAgent
from .fitness_agent import FitnessAgent
from .nutrition_agent import NutritionAgent
from .support_agent import SupportAgent

class AgentFactory:
    """Factory for creating agents"""
    
    _agents: Dict[str, BaseAgent] = {}
    
    @classmethod
    def create_agent(cls, agent_type: str) -> Optional[BaseAgent]:
        """Create an agent of the specified type"""
        if agent_type in cls._agents:
            return cls._agents[agent_type]
        
        agent_map = {
            "fitness": FitnessAgent,
            "nutrition": NutritionAgent, 
            "support": SupportAgent,
            "sales": SupportAgent,  # For now, sales uses support
            "onboarding": SupportAgent,  # For now, onboarding uses support
        }
        
        agent_class = agent_map.get(agent_type)
        if not agent_class:
            return None
        
        agent = agent_class()
        if agent.load_from_database():
            cls._agents[agent_type] = agent
            return agent
        
        return None
    
    @classmethod
    def get_agent(cls, agent_type: str) -> Optional[BaseAgent]:
        """Get an existing agent or create new one"""
        return cls.create_agent(agent_type)
    
    @classmethod
    def reload_agents(cls):
        """Reload all agents from database"""
        cls._agents.clear()
        print("🔄 Agents cache cleared, will reload from database on next request")

# Global instance
agent_factory = AgentFactory()

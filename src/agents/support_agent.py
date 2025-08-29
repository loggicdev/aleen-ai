"""
Support Agent
Handles general support and fallback cases
"""
from typing import Dict, List, Any
from .base_agent import BaseAgent

class SupportAgent(BaseAgent):
    """Support agent for general queries"""
    
    def __init__(self):
        super().__init__("Support Agent", "support")
    
    def get_tools(self) -> List[Dict]:
        """Support agent has basic tools"""
        return []  # For now, no specific tools
    
    def execute_tool(self, tool_name: str, arguments: Dict, context: Dict) -> Any:
        """Execute support tools"""
        return {"error": f"Tool {tool_name} not implemented for support agent"}

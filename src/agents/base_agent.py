"""
Base Agent
Abstract base class for all agents
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from ..services.openai_service import openai_service
from ..services.supabase_service import supabase_service

class BaseAgent(ABC):
    """Base class for all agents"""
    
    def __init__(self, name: str, agent_type: str):
        self.name = name
        self.agent_type = agent_type
        self.prompt = ""
        self.tools = []
    
    def load_from_database(self) -> bool:
        """Load agent configuration from database"""
        try:
            agents = supabase_service.get_agents()
            agent_data = next((a for a in agents if a['agent_type'] == self.agent_type), None)
            
            if agent_data:
                self.name = agent_data['name']
                self.prompt = agent_data['prompt']
                return True
            return False
        except Exception as e:
            print(f"Error loading agent {self.name}: {e}")
            return False
    
    @abstractmethod
    def get_tools(self) -> List[Dict]:
        """Get available tools for this agent"""
        pass
    
    @abstractmethod
    def execute_tool(self, tool_name: str, arguments: Dict, context: Dict) -> Any:
        """Execute a tool with given arguments"""
        pass
    
    def process_message(self, message: str, context: Dict) -> str:
        """Process a message and return response"""
        try:
            # Build messages
            messages = [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": message}
            ]
            
            # Add memory context if available
            if context.get('memory'):
                for mem in reversed(context['memory'][-5:]):  # Last 5 messages
                    messages.insert(-1, {"role": "user", "content": mem['message']})
                    messages.insert(-1, {"role": "assistant", "content": mem['response']})
            
            # Get tools
            tools = self.get_tools()
            
            # Call OpenAI
            response = openai_service.chat_completion(
                messages=messages,
                tools=tools if tools else None
            )
            
            if response.get("error"):
                return "Desculpe, tive um problema técnico. Tente novamente."
            
            # Handle tool calls
            if response.get("tool_calls"):
                tool_results = []
                for tool_call in response["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    arguments = tool_call["function"]["arguments"]
                    
                    print(f"🔧 IA solicitou uso de tools: {tool_name}")
                    result = self.execute_tool(tool_name, arguments, context)
                    tool_results.append(result)
                
                # Second call with tool results
                messages.append({"role": "assistant", "content": response["content"], "tool_calls": response["tool_calls"]})
                for i, tool_call in enumerate(response["tool_calls"]):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": str(tool_results[i])
                    })
                
                final_response = openai_service.chat_completion(messages=messages)
                return final_response.get("content", "Erro ao processar resposta.")
            
            return response.get("content", "Erro ao processar resposta.")
            
        except Exception as e:
            print(f"Error processing message in {self.name}: {e}")
            return "Desculpe, tive um problema técnico. Tente novamente."

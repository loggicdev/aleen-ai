"""
OpenAI Service
Centraliza toda comunicação com OpenAI
"""
import os
import json
from openai import OpenAI
from typing import Dict, List, Any, Optional

class OpenAIService:
    def __init__(self):
        """Initialize OpenAI client"""
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = "gpt-4o-mini"
    
    def chat_completion(
        self, 
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> Dict:
        """Create chat completion with optional tools"""
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            
            response = self.client.chat.completions.create(**kwargs)
            return self._parse_response(response)
            
        except Exception as e:
            print(f"Error in chat completion: {e}")
            return {"error": str(e)}
    
    def _parse_response(self, response) -> Dict:
        """Parse OpenAI response"""
        message = response.choices[0].message
        
        result = {
            "content": message.content,
            "role": message.role,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
        
        # Handle tool calls
        if hasattr(message, 'tool_calls') and message.tool_calls:
            result["tool_calls"] = []
            for tool_call in message.tool_calls:
                result["tool_calls"].append({
                    "id": tool_call.id,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": json.loads(tool_call.function.arguments)
                    }
                })
        
        return result

# Global instance
openai_service = OpenAIService()

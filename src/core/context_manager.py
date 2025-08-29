"""
Context Manager
Manages user context and routing logic
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from ..services.supabase_service import supabase_service

@dataclass
class UserContext:
    """User context data"""
    phone: str
    user_type: str
    has_account: bool
    onboarding_complete: bool
    is_lead: bool
    is_user: bool
    onboarding_url: Optional[str] = None

class ContextManager:
    """Manages user context and routing"""
    
    def __init__(self):
        self.fitness_keywords = [
            'treino', 'exercicio', 'musculacao', 'academia', 'workout',
            'fitness', 'peso', 'hipertrofia', 'cardio', 'serie', 'repeticao'
        ]
        
        self.nutrition_keywords = [
            'dieta', 'comida', 'receita', 'nutricao', 'alimentacao',
            'calorias', 'refeicao', 'lanche', 'jantar', 'almoco', 'cafe'
        ]
    
    def get_user_context(self, phone: str) -> UserContext:
        """Get user context from database"""
        user = supabase_service.get_user_by_phone(phone)
        
        if not user:
            return UserContext(
                phone=phone,
                user_type="lead",
                has_account=False,
                onboarding_complete=False,
                is_lead=True,
                is_user=False
            )
        
        has_onboarding = user.get('onboarding') is not None
        
        return UserContext(
            phone=phone,
            user_type="complete_user" if has_onboarding else "incomplete_user",
            has_account=True,
            onboarding_complete=has_onboarding,
            is_lead=False,
            is_user=True,
            onboarding_url=f"https://aleen.dp.claudy.host/onboarding/{user['id']}"
        )
    
    def route_to_agent(self, message: str, context: UserContext) -> str:
        """Route message to appropriate agent"""
        message_lower = message.lower()
        
        # Lead routing
        if context.user_type == "lead":
            return "sales"
        
        # Incomplete user routing  
        if context.user_type == "incomplete_user":
            return "onboarding"
        
        # Complete user routing
        if any(keyword in message_lower for keyword in self.fitness_keywords):
            return "fitness"
        elif any(keyword in message_lower for keyword in self.nutrition_keywords):
            return "nutrition"
        else:
            return "support"

# Global instance
context_manager = ContextManager()

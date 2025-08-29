"""
Tool Executor
Centraliza execução de todas as tools do sistema
"""
from typing import Dict, Any, Optional
from ..tools.fitness_tools import FitnessTools
from ..services.supabase_service import SupabaseService

class ToolExecutor:
    def __init__(self, supabase_service: SupabaseService):
        self.supabase = supabase_service
        self.fitness_tools = FitnessTools(supabase_service)
        # TODO: Adicionar nutrition_tools, base_tools, etc.
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any], context_phone: Optional[str] = None) -> Dict[str, Any]:
        """Executa uma tool específica com os argumentos fornecidos"""
        try:
            print(f"🛠️ Executando tool: {tool_name} com argumentos: {arguments}")
            
            # Fitness tools
            if tool_name == "check_user_training_plan":
                if not context_phone:
                    return {"error": "Telefone não disponível no contexto"}
                return self.fitness_tools.check_user_training_plan(context_phone)
            
            elif tool_name == "get_user_workout_plan_details":
                if not context_phone:
                    return {"error": "Telefone não disponível no contexto"}
                return self.fitness_tools.get_user_workout_plan_details(context_phone)
            
            # TODO: Adicionar outras tools conforme migradas
            # elif tool_name == "get_available_exercises":
            # elif tool_name == "create_weekly_training_plan":
            # elif tool_name == "get_user_meal_plan_details":
            # etc...
            
            else:
                return {"error": f"Tool '{tool_name}' não encontrada"}
                
        except Exception as e:
            print(f"❌ Erro ao executar tool {tool_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"error": f"Erro interno ao executar {tool_name}: {str(e)}"}
    
    def get_available_tools(self) -> list:
        """Retorna lista de tools disponíveis para os agentes"""
        # TODO: Migrar todas as tools do main.py
        return [
            "check_user_training_plan",
            "get_user_workout_plan_details",
            # Adicionar mais conforme migradas
        ]

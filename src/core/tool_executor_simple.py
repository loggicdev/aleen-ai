"""
Tool Executor Simples
Versão simplificada para testar
"""
from typing import Dict, Any, Optional, Callable

class ToolExecutor:
    def __init__(self, supabase_service=None):
        self.supabase = supabase_service
        self.tools_registry: Dict[str, Callable] = {}
        
        # Tentar importar supabase se não foi passado
        if not self.supabase:
            try:
                from src.services.supabase_service import supabase_service
                self.supabase = supabase_service
                print("✅ Supabase conectado ao ToolExecutor")
            except Exception as e:
                print(f"⚠️ Supabase não disponível: {e}")
        
        self._register_tools()
    
    def _register_tools(self):
        """Registra ferramentas disponíveis"""
        print("🔧 Registrando ferramentas...")
        
        try:
            # Importar ferramentas
            from src.tools.fitness_tools import FitnessTools
            from src.tools.nutrition_tools import NutritionTools
            from src.tools.base_tools import BaseTools
            from src.tools.analysis_tools import AnalysisTools
            
            # Instanciar ferramentas
            fitness_tools = FitnessTools(self.supabase)
            nutrition_tools = NutritionTools(self.supabase)
            base_tools = BaseTools(self.supabase)
            analysis_tools = AnalysisTools(self.supabase)
            
            # Registrar ferramentas principais
            self.tools_registry.update({
                # Fitness
                'check_user_training_plan': fitness_tools.check_user_workout_plan,
                'get_user_workout_plan_details': fitness_tools.get_user_workout_plan_details,
                
                # Nutrition
                'check_user_meal_plan': nutrition_tools.check_user_meal_plan,
                'get_user_meal_plan_details': nutrition_tools.get_user_meal_plan_details,
                'get_today_meals': nutrition_tools.get_today_meals,
                
                # Base
                'get_user_id_by_phone': base_tools.get_user_id_by_phone,
                'get_user_memory': base_tools.get_user_memory,
                'save_user_memory': base_tools.save_user_memory,
            })
            
            print(f"✅ {len(self.tools_registry)} ferramentas registradas")
            
        except Exception as e:
            print(f"❌ Erro ao registrar ferramentas: {e}")
            # Registrar ferramentas básicas como fallback
            self.tools_registry = {
                'fallback_tool': lambda *args, **kwargs: {"status": "fallback", "message": "Ferramenta não disponível"}
            }
    
    def get_openai_tools(self) -> Optional[list]:
        """Retorna ferramentas no formato OpenAI"""
        try:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "check_user_training_plan",
                        "description": "Verifica se usuário tem plano de treino ativo",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "phone": {"type": "string", "description": "Telefone do usuário"}
                            },
                            "required": ["phone"]
                        }
                    }
                },
                {
                    "type": "function", 
                    "function": {
                        "name": "get_user_workout_plan_details",
                        "description": "Obtém detalhes do plano de treino do usuário",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "phone": {"type": "string", "description": "Telefone do usuário"}
                            },
                            "required": ["phone"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "check_user_meal_plan", 
                        "description": "Verifica se usuário tem plano alimentar ativo",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "phone": {"type": "string", "description": "Telefone do usuário"}
                            },
                            "required": ["phone"]
                        }
                    }
                }
            ]
        except Exception as e:
            print(f"❌ Erro ao obter ferramentas OpenAI: {e}")
            return None
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any], phone: str) -> Dict[str, Any]:
        """Executa ferramenta específica"""
        try:
            print(f"🔧 Executando ferramenta: {tool_name}")
            
            if tool_name in self.tools_registry:
                tool_function = self.tools_registry[tool_name]
                
                # Adicionar phone aos argumentos se necessário
                if 'phone' not in arguments and phone:
                    arguments['phone'] = phone
                
                result = tool_function(**arguments)
                print(f"✅ Ferramenta {tool_name} executada")
                return result
            else:
                print(f"⚠️ Ferramenta {tool_name} não encontrada")
                return {
                    "error": f"Ferramenta {tool_name} não encontrada",
                    "available_tools": list(self.tools_registry.keys())
                }
                
        except Exception as e:
            print(f"❌ Erro ao executar {tool_name}: {e}")
            return {
                "error": f"Erro ao executar {tool_name}: {str(e)}"
            }

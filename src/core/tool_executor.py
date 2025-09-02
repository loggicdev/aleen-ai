"""
Tool Executor
Executa ferramentas de forma centralizada usando Strategy Pattern
"""
from typing import Dict, Any, Optional, Callable

# Import absoluto para evitar problemas
supabase_service = None
SupabaseService = None
try:
    from src.services.supabase_service import SupabaseService, supabase_service
except ImportError:
    try:
        from services.supabase_service import SupabaseService, supabase_service
    except ImportError:
        try:
            from ..services.supabase_service import SupabaseService, supabase_service
        except ImportError:
            print("⚠️ Supabase service não disponível")
            SupabaseService = None
            supabase_service = None

class ToolExecutor:
    def __init__(self, supabase_service=None):
        self.supabase = supabase_service or supabase_service
        self.tools_registry: Dict[str, Callable] = {}
        self._register_tools()
    
    def _register_tools(self):
        """Registra todas as ferramentas disponíveis"""
        print("🔧 [TOOLS] Iniciando registro de ferramentas...")
        
        try:
            # Import das ferramentas
            try:
                from src.tools.fitness_tools import FitnessTools
                from src.tools.nutrition_tools import NutritionTools
                from src.tools.base_tools import BaseTools
                from src.tools.analysis_tools import AnalysisTools
            except ImportError:
                try:
                    from tools.fitness_tools import FitnessTools
                    from tools.nutrition_tools import NutritionTools
                    from tools.base_tools import BaseTools
                    from tools.analysis_tools import AnalysisTools
                except ImportError:
                    from ..tools.fitness_tools import FitnessTools
                    from ..tools.nutrition_tools import NutritionTools
                    from ..tools.base_tools import BaseTools
                    from ..tools.analysis_tools import AnalysisTools
            
            print("📦 [TOOLS] Importando módulos de ferramentas...")
            
            # Instancia ferramentas
            fitness_tools = FitnessTools(self.supabase)
            nutrition_tools = NutritionTools(self.supabase)
            base_tools = BaseTools(self.supabase)
            analysis_tools = AnalysisTools(self.supabase)
            
            print("🏋️ [TOOLS] Registrando ferramentas de fitness...")
            # Registro de ferramentas de fitness
            self.tools_registry.update({
                'check_user_training_plan': fitness_tools.check_user_workout_plan,
                'get_user_workout_plan_details': fitness_tools.get_user_workout_plan_details,
                'get_user_timezone_offset_fitness': fitness_tools.get_user_timezone_offset,
            })
            
            print("🥗 [TOOLS] Registrando ferramentas de nutrição...")
            # Registro de ferramentas de nutrição
            self.tools_registry.update({
                'check_user_meal_plan': nutrition_tools.check_user_meal_plan,
                'get_user_meal_plan_details': nutrition_tools.get_user_meal_plan_details,
                'get_today_meals': nutrition_tools.get_today_meals,
                'get_user_timezone_offset_nutrition': nutrition_tools.get_user_timezone_offset,
                'create_weekly_meal_plan': nutrition_tools.create_weekly_meal_plan,
                'suggest_alternative_recipes': nutrition_tools.suggest_alternative_recipes,
                'update_meal_in_plan': nutrition_tools.update_meal_in_plan,
                'interpret_user_choice': nutrition_tools.interpret_user_choice,
                'get_recipe_ingredients': nutrition_tools.get_recipe_ingredients,
            })
            
            print("📋 [TOOLS] Registrando ferramentas base...")
            # Registro de ferramentas base
            self.tools_registry.update({
                'get_onboarding_questions': base_tools.get_onboarding_questions,
                'create_user_and_save_onboarding': base_tools.create_user_and_save_onboarding,
                'get_user_onboarding_responses': base_tools.get_user_onboarding_responses,
                'get_user_id_by_phone': base_tools.get_user_id_by_phone,
                'get_user_memory': base_tools.get_user_memory,
                'save_user_memory': base_tools.save_user_memory,
                'add_to_user_memory': base_tools.add_to_user_memory,
            })
            
            print("🔍 [TOOLS] Registrando ferramentas de análise...")
            # Registro de ferramentas de análise
            self.tools_registry.update({
                'detect_future_promises': analysis_tools.detect_future_promises,
                'analyze_onboarding_for_workout_plan': analysis_tools.analyze_onboarding_for_workout_plan,
                'execute_immediate_action': analysis_tools.execute_immediate_action,
            })
            
            print(f"✅ [TOOLS] {len(self.tools_registry)} ferramentas registradas com sucesso")
            print(f"🏋️ [TOOLS] Fitness: 3 ferramentas")
            print(f"🥗 [TOOLS] Nutrition: 8 ferramentas")
            print(f"📋 [TOOLS] Base: 7 ferramentas")
            print(f"🔍 [TOOLS] Analysis: 3 ferramentas")
            print(f"📊 [TOOLS] TOTAL: {len(self.tools_registry)} ferramentas disponíveis")
            
        except Exception as e:
            print(f"❌ [TOOLS] Erro no registro de ferramentas: {str(e)}")
            raise
    
    def get_openai_tools(self) -> Optional[list]:
        """Retorna ferramentas no formato esperado pelo OpenAI"""
        try:
            # Por enquanto, retorna uma lista básica de ferramentas principais
            # TODO: Implementar geração automática do schema de todas as ferramentas
            
            basic_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "check_user_training_plan",
                        "description": "Verifica se o usuário possui um plano de treino ativo",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "user_phone": {"type": "string", "description": "Telefone do usuário"}
                            },
                            "required": ["user_phone"]
                        }
                    }
                },
                {
                    "type": "function", 
                    "function": {
                        "name": "check_user_meal_plan",
                        "description": "Verifica se o usuário possui um plano alimentar ativo",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "user_phone": {"type": "string", "description": "Telefone do usuário"}
                            },
                            "required": ["user_phone"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_user_memory", 
                        "description": "Recupera memória/contexto do usuário",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "user_phone": {"type": "string", "description": "Telefone do usuário"}
                            },
                            "required": ["user_phone"]
                        }
                    }
                }
            ]
            
            print(f"🛠️ [TOOLS] Retornando {len(basic_tools)} ferramentas básicas para OpenAI")
            return basic_tools
            
        except Exception as e:
            print(f"❌ [TOOLS] Erro ao gerar ferramentas OpenAI: {str(e)}")
            return None
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any], context_phone: str = None) -> Dict[str, Any]:
        """Executa uma ferramenta específica"""
        try:
            print(f"🔧 [EXEC] Executando ferramenta: {tool_name}")
            print(f"📋 [EXEC] Argumentos: {list(arguments.keys()) if arguments else 'nenhum'}")
            print(f"📞 [EXEC] Contexto do telefone: {context_phone or 'não fornecido'}")
            
            if tool_name not in self.tools_registry:
                available_tools = list(self.tools_registry.keys())
                print(f"❌ [EXEC] Ferramenta '{tool_name}' não encontrada")
                print(f"🔧 [EXEC] Ferramentas disponíveis: {available_tools}")
                return {
                    "error": f"Ferramenta '{tool_name}' não encontrada",
                    "available_tools": available_tools
                }
            
            # Adiciona telefone do contexto aos argumentos se necessário
            if context_phone and 'phone_number' in self._get_tool_signature(tool_name):
                arguments['phone_number'] = context_phone
                print(f"📞 [EXEC] Telefone adicionado aos argumentos")
            
            # Executa ferramenta
            print(f"⚡ [EXEC] Iniciando execução da ferramenta...")
            tool_function = self.tools_registry[tool_name]
            result = tool_function(**arguments)
            
            # Log do resultado
            if isinstance(result, dict):
                if result.get('success'):
                    print(f"✅ [EXEC] Ferramenta '{tool_name}' executada com sucesso")
                elif result.get('error'):
                    print(f"⚠️ [EXEC] Ferramenta '{tool_name}' retornou erro: {result['error']}")
                else:
                    print(f"ℹ️ [EXEC] Ferramenta '{tool_name}' executada")
            else:
                print(f"ℹ️ [EXEC] Ferramenta '{tool_name}' retornou resultado não-dict")
            
            return result
            
        except Exception as e:
            error_msg = f"Erro ao executar ferramenta '{tool_name}': {str(e)}"
            print(f"❌ [EXEC] {error_msg}")
            return {"error": error_msg}
    
    def _get_tool_signature(self, tool_name: str) -> list:
        """Obtém assinatura da ferramenta (parâmetros esperados)"""
        try:
            import inspect
            tool_function = self.tools_registry.get(tool_name)
            if tool_function:
                sig = inspect.signature(tool_function)
                return list(sig.parameters.keys())
            return []
        except:
            return []
    
    def list_available_tools(self) -> Dict[str, Any]:
        """Lista todas as ferramentas disponíveis"""
        tools_info = {}
        
        for tool_name, tool_function in self.tools_registry.items():
            try:
                import inspect
                signature = inspect.signature(tool_function)
                tools_info[tool_name] = {
                    "parameters": list(signature.parameters.keys()),
                    "docstring": tool_function.__doc__ or "Sem descrição disponível"
                }
            except:
                tools_info[tool_name] = {
                    "parameters": [],
                    "docstring": "Erro ao obter informações"
                }
        
        return {
            "total_tools": len(tools_info),
            "tools": tools_info
        }
    
    def validate_tool_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Valida argumentos antes da execução"""
        if tool_name not in self.tools_registry:
            return {
                "valid": False,
                "error": f"Ferramenta '{tool_name}' não existe"
            }
        
        try:
            import inspect
            tool_function = self.tools_registry[tool_name]
            signature = inspect.signature(tool_function)
            
            # Verifica parâmetros obrigatórios
            required_params = [
                name for name, param in signature.parameters.items()
                if param.default == inspect.Parameter.empty
            ]
            
            missing_params = [
                param for param in required_params
                if param not in arguments
            ]
            
            if missing_params:
                return {
                    "valid": False,
                    "error": f"Parâmetros obrigatórios ausentes: {missing_params}"
                }
            
            return {"valid": True}
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Erro na validação: {str(e)}"
            }

# Factory function
def create_tool_executor() -> ToolExecutor:
    try:
        from services.supabase_service import supabase_service
    except ImportError:
        from ..services.supabase_service import supabase_service
    return ToolExecutor(supabase_service)

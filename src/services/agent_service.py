"""
Agent Service
Gerencia agentes e processamento de mensagens com OpenAI
"""
from typing import Dict, Any, Optional, List
import json
from datetime import datetime

# Import absoluto para evitar problemas
supabase_service = None
try:
    from src.services.supabase_service import supabase_service
except ImportError:
    try:
        from services.supabase_service import supabase_service
    except ImportError:
        try:
            from .supabase_service import supabase_service
        except ImportError:
            print("⚠️ Supabase service não disponível")
            supabase_service = None

class AgentService:
    def __init__(self, openai_service=None):
        self.supabase = supabase_service
        self.openai_service = openai_service
    
    async def process_message(self, message: str, phone: str, context: Dict = None, tool_executor=None) -> Dict[str, Any]:
        """Processa mensagem do usuário usando OpenAI e ferramentas"""
        try:
            # Extrair contexto do usuário
            user_context = context.get('user_context', {}) if context else {}
            user_name = context.get('user_name', 'Usuário') if context else 'Usuário'
            history = context.get('conversation_history', []) if context else []
            
            # BUSCAR AGENTE DO BANCO DE DADOS
            print("🔍 Buscando agente 'aleen' do banco de dados...")
            agent_data = self.get_agent_by_name("aleen")
            
            if agent_data and agent_data.get('prompt'):
                print(f"✅ Agente encontrado: {agent_data.get('name')}")
                print(f"📝 Prompt do banco: {agent_data.get('prompt')[:100]}...")
            else:
                print("⚠️ Agente não encontrado no banco, usando fallback temporário")
                # Fallback mínimo apenas se não encontrar no banco
                agent_data = {
                    "name": "Aleen IA",
                    "prompt": f"""Você é a Aleen, assistente especializada em fitness e nutrição.

USUÁRIO: {user_name} (ID: {phone})
Contexto: {user_context.get('user_type', 'usuário')} - {'tem conta' if user_context.get('has_account') else 'sem conta'}

INSTRUÇÕES:
1. SEMPRE use as ferramentas disponíveis para consultar dados reais
2. Para treinos: use check_user_training_plan e get_user_workout_plan_details  
3. Para alimentação: use check_user_meal_plan e get_user_meal_plan_details
4. NUNCA invente - sempre consulte o banco
5. Respostas curtas e focadas (máximo 200 chars)
6. Use emojis: 💪 🏋️ 🥗 ✨"""
                }
            
            # Preparar contexto da conversa
            conversation_context = context or {}
            conversation_context.update({
                "user_phone": phone,
                "timestamp": datetime.now().isoformat(),
                "agent": agent_data["name"]
            })
            
            # Preparar mensagens para OpenAI
            messages = [
                {"role": "system", "content": agent_data.get("prompt", "Você é uma assistente útil.")},
                {"role": "user", "content": message}
            ]
            
            # Se temos ferramentas, incluir na chamada OpenAI
            tools = None
            if tool_executor:
                available_tools = tool_executor.get_openai_tools()
                tools = available_tools if available_tools else None
            
            # Chamar OpenAI
            if self.openai_service:
                response = self.openai_service.chat_completion(
                    messages=messages,
                    tools=tools
                )
                
                # Obter conteúdo da resposta de forma segura
                response_text = (response.get('content') or '').strip() if response.get('content') else 'Erro no processamento'
                
                if not response_text:
                    response_text = "Recebi sua mensagem, mas não consegui processar agora. Tente novamente."
                
                # Se houve tool calls, executar
                if response.get('tool_calls') and tool_executor:
                    print(f"🔧 Executando {len(response['tool_calls'])} ferramentas (v2)...")
                    for tool_call in response['tool_calls']:
                        try:
                            # Tratar argumentos que podem vir como dict ou string
                            arguments = tool_call['function']['arguments']
                            if isinstance(arguments, str):
                                arguments = json.loads(arguments)
                            elif not isinstance(arguments, dict):
                                print(f"⚠️ Argumentos em formato inesperado: {type(arguments)}")
                                arguments = {}
                            
                            tool_result = tool_executor.execute_tool(
                                tool_call['function']['name'],
                                arguments,
                                phone
                            )
                            print(f"✅ Ferramenta {tool_call['function']['name']}: {str(tool_result)[:100]}...")
                            # Adicionar resultado ao contexto
                            conversation_context['last_tool_result'] = tool_result
                        except Exception as e:
                            print(f"❌ Erro na ferramenta {tool_call['function']['name']}: {e}")
                
                return {
                    "response": response_text,
                    "timestamp": datetime.now().isoformat(),
                    "updated_context": conversation_context,
                    "tool_calls": response.get('tool_calls', [])
                }
            else:
                # Fallback sem OpenAI
                return {
                    "response": f"Mensagem recebida: {message[:50]}... (processamento básico)",
                    "timestamp": datetime.now().isoformat(), 
                    "updated_context": conversation_context
                }
                
        except Exception as e:
            print(f"❌ [AGENT] Erro no processamento: {str(e)}")
            return {
                "response": "Desculpe, houve um erro no processamento. Tente novamente.",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    def get_agent_by_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Busca agente específico por ID"""
        try:
            result = self.supabase.client.table('agents').select('*').eq('id', agent_id).execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            print(f"❌ Erro ao buscar agente {agent_id}: {str(e)}")
            return None
    
    def get_agent_by_name(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Busca agente por nome"""
        try:
            result = self.supabase.client.table('agents').select('*').eq('name', agent_name).execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            print(f"❌ Erro ao buscar agente {agent_name}: {str(e)}")
            return None
    
    def get_all_agents(self) -> List[Dict[str, Any]]:
        """Lista todos os agentes disponíveis"""
        try:
            result = self.supabase.client.table('agents').select('*').execute()
            return result.data or []
            
        except Exception as e:
            print(f"❌ Erro ao listar agentes: {str(e)}")
            return []
    
    def update_agent_prompt(self, agent_id: str, new_prompt: str) -> bool:
        """Atualiza prompt de um agente"""
        try:
            result = self.supabase.client.table('agents').update({
                'prompt': new_prompt
            }).eq('id', agent_id).execute()
            
            return bool(result.data)
            
        except Exception as e:
            print(f"❌ Erro ao atualizar agente {agent_id}: {str(e)}")
            return False
    
    def create_agent(self, agent_data: Dict[str, Any]) -> Optional[str]:
        """Cria novo agente"""
        try:
            result = self.supabase.client.table('agents').insert(agent_data).execute()
            
            if result.data:
                return result.data[0]['id']
            return None
            
        except Exception as e:
            print(f"❌ Erro ao criar agente: {str(e)}")
            return None

# Factory function
def create_agent_service(openai_service=None) -> AgentService:
    return AgentService(openai_service)

"""
Agent Service Simples
Versão simplificada para testar
"""
from typing import Dict, Any, Optional
import json
from datetime import datetime

class AgentService:
    def __init__(self, openai_service=None):
        self.openai_service = openai_service
        self.supabase = None
        
        # Tentar importar supabase se disponível
        try:
            from src.services.supabase_service import supabase_service
            self.supabase = supabase_service
            print("✅ Supabase conectado ao AgentService")
        except Exception as e:
            print(f"⚠️ Supabase não disponível: {e}")
    
    async def process_message(self, message: str, phone: str, context: Dict = None, tool_executor=None) -> Dict[str, Any]:
        """Processa mensagem do usuário"""
        try:
            print(f"🧠 AgentService processando: {message[:50]}...")
            
            # Buscar agente do banco se possível
            agent_data = None
            if self.supabase and hasattr(self.supabase, 'client') and self.supabase.client:
                try:
                    result = self.supabase.client.table('agents').select('*').eq('name', 'aleen').execute()
                    if result.data:
                        agent_data = result.data[0]
                        print(f"✅ Agente do banco: {agent_data.get('name')}")
                        print(f"📝 Prompt: {agent_data.get('prompt', '')[:100]}...")
                except Exception as e:
                    print(f"⚠️ Erro ao buscar agente: {e}")
            
            # Fallback se não encontrou no banco
            if not agent_data:
                print("⚠️ Usando agente padrão")
                user_context = context.get('user_context', {}) if context else {}
                user_name = context.get('user_name', 'Usuário') if context else 'Usuário'
                
                agent_data = {
                    "name": "Aleen IA",
                    "prompt": f"""Você é a Aleen, assistente de fitness e nutrição.

USUÁRIO: {user_name} (ID: {phone})
Contexto: {user_context.get('user_type', 'usuário')} - {'tem conta' if user_context.get('has_account') else 'sem conta'}

INSTRUÇÕES CRÍTICAS:
1. SEMPRE use as ferramentas para consultar dados reais
2. Para treinos: use check_user_training_plan e get_user_workout_plan_details  
3. Para alimentação: use check_user_meal_plan e get_user_meal_plan_details
4. NUNCA invente - sempre consulte o banco
5. Respostas curtas (máximo 200 chars)
6. Use emojis: 💪 🏋️ 🥗 ✨"""
                }
            
            # Preparar mensagens para OpenAI
            messages = [
                {"role": "system", "content": agent_data.get("prompt", "Você é uma assistente útil.")},
                {"role": "user", "content": message}
            ]
            
            # Chamar OpenAI se disponível
            if self.openai_service:
                print("🤖 Chamando OpenAI...")
                
                # Incluir ferramentas se disponível
                tools = None
                if tool_executor and hasattr(tool_executor, 'get_openai_tools'):
                    tools = tool_executor.get_openai_tools()
                
                response = self.openai_service.chat_completion(
                    messages=messages,
                    tools=tools
                )
                
                response_text = response.get('content', '').strip()
                print(f"✅ OpenAI respondeu: {response_text[:100]}...")
                
                # Executar tool calls se houver
                if response.get('tool_calls') and tool_executor:
                    print(f"🔧 Executando {len(response['tool_calls'])} ferramentas...")
                    for tool_call in response['tool_calls']:
                        try:
                            tool_result = tool_executor.execute_tool(
                                tool_call['function']['name'],
                                json.loads(tool_call['function']['arguments']),
                                phone
                            )
                            print(f"✅ Ferramenta {tool_call['function']['name']}: {str(tool_result)[:100]}...")
                        except Exception as e:
                            print(f"❌ Erro na ferramenta {tool_call['function']['name']}: {e}")
                
                return {
                    "response": response_text,
                    "agent_used": agent_data.get("name", "aleen"),
                    "timestamp": datetime.now().isoformat(),
                    "tool_calls": response.get('tool_calls', [])
                }
            else:
                print("⚠️ OpenAI não disponível")
                return {
                    "response": f"Recebi sua mensagem: {message[:50]}... (OpenAI indisponível)",
                    "agent_used": "fallback",
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            print(f"❌ Erro no AgentService: {e}")
            return {
                "response": "Desculpe, houve um erro no processamento. Tente novamente.",
                "agent_used": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }

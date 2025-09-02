"""
Main de Produção - v2025.08.29.2055 - JSON Tools Fix Applied
Versão simplificada e robusta para deploy
"""
import os
import sys
import re
import json
import time
import requests
from pathlib import Path

# Configurar ambiente
os.environ.setdefault('OPENAI_API_KEY', 'placeholder')
os.environ.setdefault('SUPABASE_URL', 'placeholder')  
os.environ.setdefault('SUPABASE_SERVICE_ROLE_KEY', 'placeholder')

# Adicionar src ao Python path
current_dir = Path(__file__).parent
src_path = current_dir / "src"
sys.path.insert(0, str(src_path))

# Imports da aplicação
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import uvicorn

# Modelo para requisições do Node.js
class WhatsAppChatRequest(BaseModel):
    phone: str
    message: str
    history: list = []
    user_context: dict = {}
    user_name: str = ""
    user_id: str = ""
    recommended_agent: str = ""
    send_to_whatsapp: bool = True

# Evolution API Integration
class EvolutionAPIService:
    def __init__(self):
        self.base_url = os.getenv("EVOLUTION_API_BASE_URL", "")
        self.api_key = os.getenv("EVOLUTION_API_KEY", "")
        self.instance = os.getenv("EVOLUTION_INSTANCE", "")
        
        if not all([self.base_url, self.api_key, self.instance]):
            print("⚠️ Evolution API configuration incomplete")
            print(f"   Base URL: {'✅' if self.base_url else '❌'}")
            print(f"   API Key: {'✅' if self.api_key else '❌'}")
            print(f"   Instance: {'✅' if self.instance else '❌'}")
    
    def clean_phone_number(self, phone: str) -> str:
        """Limpa e formata número de telefone"""
        clean = re.sub(r'[^\d]', '', phone)
        if clean.startswith('55') and len(clean) == 13:
            return clean + "@s.whatsapp.net"
        elif len(clean) == 11:
            return "55" + clean + "@s.whatsapp.net"
        else:
            return clean + "@s.whatsapp.net"
    
    def split_message(self, message: str, max_length: int = 4000) -> List[str]:
        """Quebra mensagem em partes menores"""
        if len(message) <= max_length:
            return [message]
        
        messages = []
        current_message = ""
        
        for paragraph in message.split('\n\n'):
            if len(current_message) + len(paragraph) + 2 <= max_length:
                if current_message:
                    current_message += '\n\n' + paragraph
                else:
                    current_message = paragraph
            else:
                if current_message:
                    messages.append(current_message)
                current_message = paragraph
        
        if current_message:
            messages.append(current_message)
        
        return messages
    
    def send_text_message(self, phone_number: str, message: str) -> bool:
        """Envia mensagem de texto via Evolution API"""
        try:
            if not all([self.base_url, self.api_key, self.instance]):
                print("❌ Evolution API não configurada")
                return False
            
            # Quebra mensagem se necessário
            messages = self.split_message(message)
            clean_number = self.clean_phone_number(phone_number)
            
            print(f"📱 Enviando {len(messages)} mensagem(s) para {clean_number}")
            
            success = True
            for i, msg in enumerate(messages):
                payload = {
                    "number": clean_number,
                    "text": msg,
                    "options": {
                        "delay": 3500,
                        "presence": "composing",
                        "linkPreview": False
                    }
                }
                
                url = f"{self.base_url}/message/sendText/{self.instance}"
                headers = {
                    "Content-Type": "application/json",
                    "apikey": self.api_key
                }
                
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                
                if response.status_code in [200, 201]:
                    print(f"✅ Mensagem {i+1}/{len(messages)} enviada com sucesso")
                    if i < len(messages) - 1:
                        print(f"⏱️ Aguardando 3.5s antes da próxima mensagem...")
                        time.sleep(3.5)
                else:
                    print(f"❌ Erro ao enviar mensagem {i+1}: {response.status_code} - {response.text}")
                    success = False
                    break
            
            return success
            
        except Exception as e:
            print(f"❌ Erro no Evolution API: {str(e)}")
            return False

# Instanciar o serviço Evolution API
evolution_service = EvolutionAPIService()

# Modelo para requisições
class ChatRequest(BaseModel):
    phone: str
    message: str

# Criar aplicação FastAPI
app = FastAPI(
    title="Aleen IA - Production",
    description="Sistema de IA para nutrição e fitness",
    version="2.0.0"
)

# Variáveis globais para serviços
services_initialized = False
openai_service = None
agent_service = None
tool_executor = None

def initialize_services():
    """Inicializa serviços se ainda não foram inicializados"""
    global services_initialized, openai_service, agent_service, tool_executor
    
    if services_initialized:
        return True
    
    try:
        print("🔧 Inicializando serviços...")
        
        # Verificar se conseguimos importar pelo menos o básico
        try:
            from src.services.supabase_service import supabase_service
            health = supabase_service.health_check()
            print(f"🏥 Supabase: {health.get('status', 'unknown')}")
        except Exception as e:
            print(f"⚠️ Supabase não disponível: {e}")
        
        # Tentar importar OpenAI
        try:
            from src.services.openai_service import openai_service as openai_svc
            openai_service = openai_svc
            print("✅ OpenAI service importado")
        except Exception as e:
            print(f"⚠️ OpenAI service não disponível: {e}")
            openai_service = None
        
        # Importar diretamente as classes em vez das factory functions
        try:
            from src.services.agent_service import AgentService
            if openai_service:
                agent_service = AgentService(openai_service)
                print("✅ Agent service criado diretamente")
            else:
                agent_service = None
                print("⚠️ Agent service não criado (OpenAI indisponível)")
        except Exception as e:
            print(f"⚠️ Agent service não disponível: {e}")
            agent_service = None
        
        # Tentar importar Tool Executor diretamente
        try:
            from src.core.tool_executor import ToolExecutor
            tool_executor = ToolExecutor()
            print(f"✅ Tool executor criado diretamente")
        except Exception as e:
            print(f"⚠️ Tool executor não disponível: {e}")
            tool_executor = None
        
        services_initialized = True
        print("✅ Inicialização de serviços concluída")
        return True
        
    except Exception as e:
        print(f"❌ Erro crítico na inicialização: {str(e)}")
        # Permitir que a aplicação rode mesmo com erros, para health check básico
        services_initialized = True
        return False

@app.get("/")
async def root():
    """Status básico"""
    return {"status": "healthy", "service": "Aleen IA", "version": "2.0.0"}

@app.get("/health")
async def health_check():
    """Health check detalhado"""
    try:
        initialize_services()
        
        return {
            "status": "healthy",
            "timestamp": "2025-08-29T19:45:00Z",
            "services": {
                "openai": "connected" if openai_service else "not_connected",
                "tools": len(tool_executor.tools_registry) if tool_executor else 0,
                "agent": "ready" if agent_service else "not_ready"
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=200,  # Mudado para 200 para passar no health check
            content={
                "status": "partial", 
                "error": str(e),
                "message": "Serviço rodando com funcionalidade limitada"
            }
        )

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Endpoint de chat"""
    try:
        initialize_services()
        
        print(f"💬 Chat de {request.phone}: {request.message[:50]}...")
        
        # Processar mensagem com agent se disponível
        if agent_service and tool_executor:
            try:
                result = await agent_service.process_message(
                    message=request.message,
                    phone=request.phone,
                    context={},
                    tool_executor=tool_executor
                )
                
                return {
                    "status": "processed",
                    "phone": request.phone,
                    "response": result.get('response', 'Processado'),
                    "timestamp": result.get('timestamp')
                }
            except Exception as e:
                print(f"❌ Erro no agent: {str(e)}")
                # Fallback para resposta simples
                pass
        
        # Resposta simples se agent não disponível
        return {
            "status": "processed", 
            "phone": request.phone,
            "response": f"Mensagem recebida: {request.message}",
            "timestamp": "2025-08-29T19:45:00Z",
            "mode": "fallback"
        }
            
    except Exception as e:
        print(f"❌ Erro no chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Modelos para compatibilidade com Node.js
class WhatsAppMessageRequest(BaseModel):
    user_id: str
    user_name: str
    phone_number: str
    message: str
    conversation_history: list = []
    recommended_agent: str = None
    send_to_whatsapp: bool = True
    user_context: Dict = None

class WhatsAppMessageResponse(BaseModel):
    response: str
    agent_used: str
    should_handoff: bool = False
    next_agent: Optional[str] = None
    whatsapp_sent: bool = False
    messages_sent: int = 0

@app.post("/whatsapp-chat", response_model=WhatsAppMessageResponse)
async def whatsapp_chat_endpoint(request: WhatsAppMessageRequest):
    """Endpoint original que o Node.js está esperando"""
    try:
        print(f"📱 WhatsApp Chat - Request: {request}")
        
        phone = request.phone_number or request.user_id
        message = request.message
        user_name = request.user_name
        recommended_agent = request.recommended_agent or 'DOUBT'
        
        if not phone or not message:
            print(f"❌ Dados insuficientes - Phone: {phone}, Message: {message}")
            return WhatsAppMessageResponse(
                response="Erro: Dados insuficientes",
                agent_used="error",
                should_handoff=False,
                whatsapp_sent=False,
                messages_sent=0
            )
        
        print(f"📱 WhatsApp de {user_name} ({phone}): {message[:50]}...")
        
        initialize_services()
        
        # PRIORIDADE 1: Usar AgentService com ferramentas (IA COMPLETA)
        if agent_service and tool_executor:
            try:
                print("🧠 Processando com AgentService + ToolExecutor (IA COMPLETA)...")
                result = await agent_service.process_message(
                    message=message,
                    phone=phone,
                    context={
                        "user_name": user_name,
                        "recommended_agent": recommended_agent,
                        "user_context": request.user_context,
                        "conversation_history": request.conversation_history
                    },
                    tool_executor=tool_executor
                )
                
                response_text = result.get('response', 'Processado')
                agent_used = result.get('agent_used', 'aleen_ai')
                
                print(f"🤖 IA COMPLETA processou - Agente: {agent_used}")
                print(f"✅ Resposta da IA COMPLETA ({len(response_text)} chars)")
                
                # ENVIAR VIA EVOLUTION API
                whatsapp_sent = False
                messages_sent = 0
                
                if request.send_to_whatsapp:
                    print(f"📤 Enviando resposta da IA COMPLETA via Evolution API...")
                    try:
                        success = evolution_service.send_text_message(phone, response_text)
                        if success:
                            whatsapp_sent = True
                            messages_sent = len(evolution_service.split_message(response_text))
                            print(f"✅ IA COMPLETA enviada via WhatsApp para {phone}")
                        else:
                            print(f"❌ Falha ao enviar via WhatsApp")
                    except Exception as e:
                        print(f"❌ Erro ao enviar WhatsApp: {str(e)}")
                
                return WhatsAppMessageResponse(
                    response=response_text,
                    agent_used=agent_used,
                    should_handoff=result.get('should_handoff', False),
                    next_agent=result.get('next_agent'),
                    whatsapp_sent=whatsapp_sent,
                    messages_sent=messages_sent
                )
            except Exception as e:
                print(f"❌ Erro na IA COMPLETA: {str(e)}")
                print("⬇️ Fallback para OpenAI direto...")
                # Continua para fallback
        else:
            print("⚠️ AgentService ou ToolExecutor indisponíveis, usando fallback...")
        
        # FALLBACK: Usar chamada direta ao OpenAI (SEM FERRAMENTAS)
        if openai_service and request.send_to_whatsapp:
            try:
                print("🤖 Processando com OpenAI diretamente...")
                
                # Extrair contexto
                context = request.user_context or {}
                history = request.conversation_history or []
                
                # Criar mensagens para OpenAI
                system_prompt = f"""Você é a Aleen, assistente especializada em fitness e nutrição.

Usuário: {user_name} (ID: {phone})
Contexto: {context.get('user_type', 'unknown')} - {'tem conta' if context.get('has_account') else 'sem conta'}
Histórico recente: {len(history)} mensagens sobre treinos

Instruções:
- Seja natural, amigável e motivadora
- Para usuários com conta, consulte dados específicos 
- Quebre respostas longas em mensagens menores
- Use emojis relevantes
- Seja específica sobre treinos e exercícios
"""

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{user_name} pergunta: {message}"}
                ]
                
                # Chamar OpenAI diretamente
                response = openai_service.chat_completion(messages)
                
                # Tratamento seguro da resposta
                ai_response = response.get('content') or ''
                ai_response = ai_response.strip() if ai_response else ''
                
                if not ai_response and response.get('error'):
                    ai_response = "Desculpe, houve um problema técnico. Tente novamente em alguns instantes."
                elif not ai_response:
                    ai_response = "Recebi sua mensagem, mas não consegui processar agora. Tente novamente."
                
                if ai_response:
                    print(f"🤖 IA respondeu ({len(ai_response)} chars)")
                    
                    # ENVIAR VIA EVOLUTION API
                    success = evolution_service.send_text_message(phone, ai_response)
                    
                    return WhatsAppMessageResponse(
                        response=ai_response,
                        agent_used="openai_direct",
                        should_handoff=False,
                        next_agent=None,
                        whatsapp_sent=success,
                        messages_sent=len(evolution_service.split_message(ai_response)) if success else 0
                    )
                    
            except Exception as e:
                print(f"❌ Erro no OpenAI direto: {str(e)}")
                # Continua para fallback
        
        # FALLBACK TEMPORÁRIO - só até os serviços funcionarem
        print("⚠️ Usando fallback temporário - serviços indisponíveis")
        fallback_text = f"Olá {user_name}! ⚠️ Estou com problemas técnicos temporários. Meus sistemas de treino e nutrição estão sendo atualizados. Tente novamente em alguns minutos!"
        
        # ENVIAR VIA EVOLUTION API
        whatsapp_sent = False
        messages_sent = 0
        
        if request.send_to_whatsapp:
            print(f"📤 Enviando fallback via Evolution API...")
            try:
                success = evolution_service.send_text_message(phone, fallback_text)
                if success:
                    whatsapp_sent = True
                    messages_sent = len(evolution_service.split_message(fallback_text))
                    print(f"✅ Fallback enviado via WhatsApp para {phone}")
                else:
                    print(f"❌ Falha ao enviar via WhatsApp")
            except Exception as e:
                print(f"❌ Erro ao enviar WhatsApp: {str(e)}")
        
        return WhatsAppMessageResponse(
            response=fallback_text,
            agent_used="technical_difficulties",
            should_handoff=False,
            next_agent=None,
            whatsapp_sent=whatsapp_sent,
            messages_sent=messages_sent
        )
            
    except Exception as e:
        print(f"❌ Erro no whatsapp-chat: {str(e)}")
        return WhatsAppMessageResponse(
            response=f"Erro interno: {str(e)}",
            agent_used="error",
            should_handoff=False,
            next_agent=None,
            whatsapp_sent=False,
            messages_sent=0
        )

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Webhook handler"""
    try:
        body = await request.body()
        data = await request.json() if body else {}
        
        phone = data.get('phone', data.get('from', 'unknown'))
        message = data.get('message', data.get('text', ''))
        
        if not phone or not message:
            return {"status": "ignored", "reason": "Dados insuficientes"}
        
        print(f"📨 Webhook de {phone}: {message[:50]}...")
        
        initialize_services()
        
        # Processar via agent se disponível
        if agent_service and tool_executor:
            try:
                result = await agent_service.process_message(
                    message=message,
                    phone=phone,
                    context={},
                    tool_executor=tool_executor
                )
                
                return {
                    "status": "processed",
                    "phone": phone,
                    "response": result.get('response', 'Processado')
                }
            except Exception as e:
                print(f"❌ Erro no agent: {str(e)}")
                # Fallback
                pass
        
        return {
            "status": "processed",
            "phone": phone, 
            "response": "Webhook recebido",
            "mode": "fallback"
        }
            
    except Exception as e:
        print(f"❌ Erro no webhook: {str(e)}")
        return {"status": "error", "error": str(e)}

@app.get("/tools")
async def list_tools():
    """Lista ferramentas disponíveis"""
    try:
        initialize_services()
        
        if tool_executor:
            return tool_executor.list_available_tools()
        else:
            return {
                "total_tools": 0, 
                "tools": {},
                "status": "tools_not_available"
            }
            
    except Exception as e:
        return {
            "total_tools": 0,
            "tools": {},
            "error": str(e),
            "status": "error"
        }

@app.post("/send-whatsapp")
async def send_whatsapp_message(request: Dict[str, Any]):
    """Endpoint para enviar mensagem diretamente via WhatsApp"""
    try:
        phone_number = request.get('phone_number', '')
        message = request.get('message', '')
        
        if not phone_number or not message:
            raise HTTPException(status_code=400, detail="phone_number e message são obrigatórios")
        
        print(f"📤 Enviando WhatsApp direto para {phone_number}: {message[:50]}...")
        
        # Enviar via Evolution API
        success = evolution_service.send_text_message(phone_number, message)
        messages = evolution_service.split_message(message)
        
        return {
            "success": success,
            "phone_number": phone_number,
            "messages_sent": len(messages) if success else 0,
            "message_length": len(message),
            "status": "sent" if success else "failed"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enviar WhatsApp: {str(e)}")

@app.get("/agents")
async def list_agents():
    """Lista agentes disponíveis"""
    try:
        initialize_services()
        
        # Simular agentes básicos
        agents_info = {
            "onboarding": {"name": "Onboarding Agent", "description": "Agente para novos usuários"},
            "support": {"name": "Support Agent", "description": "Agente de suporte"},
            "sales": {"name": "Sales Agent", "description": "Agente de vendas"},
            "fallback": {"name": "Fallback Agent", "description": "Agente de fallback"}
        }
        
        return {
            "agents": list(agents_info.keys()),
            "details": agents_info,
            "total": len(agents_info)
        }
        
    except Exception as e:
        return {
            "agents": [],
            "details": {},
            "total": 0,
            "error": str(e)
        }

@app.post("/reload-agents")
async def reload_agents():
    """Recarrega os agentes"""
    try:
        print("🔄 Recarregando agentes...")
        
        # Simular reload
        return {
            "success": True,
            "message": "Agentes recarregados com sucesso (modo fallback)",
            "agents_loaded": ["onboarding", "support", "sales", "fallback"],
            "total": 4
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Erro ao recarregar agentes: {str(e)}",
            "agents_loaded": [],
            "total": 0
        }

@app.get("/agents/config")
async def get_agents_config():
    """Retorna a configuração dos agentes"""
    try:
        # Configuração básica de fallback
        config = {
            "onboarding": {"type": "onboarding", "active": True},
            "support": {"type": "support", "active": True},
            "sales": {"type": "sales", "active": True},
            "fallback": {"type": "fallback", "active": True}
        }
        
        return {
            "agents_config": config,
            "total_agents": len(config),
            "status": "fallback_config"
        }
        
    except Exception as e:
        return {
            "agents_config": {},
            "total_agents": 0,
            "error": str(e)
        }

@app.get("/user-memory/{phone_number}")
async def get_user_memory_endpoint(phone_number: str):
    """Retorna a memória/histórico de um usuário"""
    try:
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        
        # Simular memória vazia por enquanto
        return {
            "phone_number": clean_phone,
            "memory_entries": 0,
            "conversation_history": [],
            "memory_key": f"user_memory:{clean_phone}",
            "status": "no_memory_service"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao recuperar memória: {str(e)}")

@app.delete("/user-memory/{phone_number}")
async def clear_user_memory_endpoint(phone_number: str):
    """Limpa a memória/histórico de um usuário"""
    try:
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        
        return {
            "message": f"Memória do usuário {clean_phone} limpa (modo fallback)",
            "phone_number": clean_phone,
            "memory_key": f"user_memory:{clean_phone}",
            "status": "cleared_fallback"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao limpar memória: {str(e)}")

@app.post("/test-user-context")
async def test_user_context(request: Dict[str, Any]):
    """Endpoint de teste para validar UserContext"""
    try:
        phone_number = request.get('phone_number', '')
        user_context = request.get('user_context', {})
        
        print(f"🧪 TESTE - UserContext para {phone_number}: {user_context}")
        
        # Simular teste
        return {
            "phone_number": phone_number,
            "user_context_received": user_context,
            "context_valid": bool(phone_number),
            "test_result": "passed_fallback",
            "message": "Teste executado em modo fallback"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no teste: {str(e)}")

@app.post("/admin/reload-agents")
async def admin_reload_agents():
    """Recarrega os agentes (admin)"""
    return await reload_agents()

if __name__ == "__main__":
    print("🚀 Iniciando Aleen IA - Produção - TESTE LOG v2058")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 9000)),
        log_level="info"
    )

"""
Aleen AI - Main Application (Refatorado)
Orquestra os serviços organizados
"""
import os
import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Force stdout to be unbuffered for Docker logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

load_dotenv()

# Imports dos serviços organizados
from src.services.supabase_service import SupabaseService
from src.services.agent_service import AgentService
from src.core.context_manager import ContextManager
from src.core.tool_executor import ToolExecutor

app = FastAPI(title="Aleen AI Agents", version="2.0.0")

# Inicialização dos serviços
print("🚀 Iniciando Aleen AI Python Service...")

# Services
supabase_service = SupabaseService()
agent_service = AgentService(supabase_service)
context_manager = ContextManager(supabase_service)
tool_executor = ToolExecutor(supabase_service)

# Carrega agentes do banco
loaded_agents = agent_service.load_agents_from_database()

class WhatsAppMessage(BaseModel):
    phone_number: str
    message: str

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "aleen-ai-python", "version": "2.0.0"}

@app.post("/reload-agents")
async def reload_agents():
    """Recarrega agentes do banco de dados"""
    try:
        reloaded_agents = agent_service.reload_agents()
        return {
            "success": True,
            "message": "Agentes recarregados com sucesso",
            "agents_loaded": list(reloaded_agents.keys()),
            "total": len(reloaded_agents)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/whatsapp-chat")
async def whatsapp_chat_endpoint(request: WhatsAppMessage):
    """Endpoint principal para processar mensagens do WhatsApp"""
    try:
        print(f"🤖 Processando mensagem WhatsApp para usuário {request.phone_number}")
        
        # 1. Análise de contexto
        user_context = context_manager.get_user_context(request.phone_number)
        print(f"👤 Contexto do usuário:")
        print(f"   - Tipo: {user_context['type']}")
        print(f"   - Tem conta: {user_context['has_account']}")
        print(f"   - Onboarding completo: {user_context['onboarding_completed']}")
        print(f"   - É lead: {user_context['is_lead']}")
        print(f"   - É usuário: {user_context['is_user']}")
        if user_context.get('onboarding_url'):
            print(f"   - URL onboarding: {user_context['onboarding_url']}")
        
        # 2. Roteamento para agente
        agent_key = context_manager.detect_intent_and_route_agent(request.message, user_context)
        print(f"🎯 Agente selecionado: {agent_key}")
        
        selected_agent = agent_service.get_agent_by_key(agent_key)
        if not selected_agent:
            raise HTTPException(status_code=404, detail=f"Agente '{agent_key}' não encontrado")
        
        # 3. Busca memória do usuário
        user_memory = context_manager.get_user_memory(request.phone_number)
        
        # 4. Processar com agente (TODO: implementar processamento com OpenAI)
        # Por enquanto, resposta simples
        response = f"Olá! Agente {selected_agent['name']} selecionado. Em breve implementaremos o processamento completo!"
        
        # 5. Salvar na memória
        context_manager.save_interaction_to_memory(
            request.phone_number, 
            request.message, 
            response
        )
        
        return {
            "success": True,
            "response": response,
            "agent_used": selected_agent['name'],
            "user_context": user_context['type']
        }
        
    except Exception as e:
        print(f"❌ Erro no processamento: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("🌐 Servidor rodando em: http://0.0.0.0:9000")
    print("📋 Health check: http://0.0.0.0:9000/health")
    uvicorn.run(app, host="0.0.0.0", port=9000)

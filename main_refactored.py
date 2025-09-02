"""
Main Refactored - Nova arquitetura modular
Substitui o main.py monolítico por uma estrutura organizada
"""
import os
import sys
from pathlib import Path

# Adiciona src ao PYTHONPATH para imports relativos
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Imports da aplicação
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
from typing import Dict, Any
from pydantic import BaseModel

# Imports dos serviços refatorados
from src.services.supabase_service import supabase_service
from src.services.openai_service import create_openai_service
from src.services.agent_service import create_agent_service
from src.core.context_manager import context_manager
from src.core.tool_executor import create_tool_executor
from src.core.logger import logger
from src.api.routes import router, init_routes

# Modelo para requisições de chat
class ChatRequest(BaseModel):
    phone: str
    message: str
    
# Instâncias globais dos serviços
openai_service = None
agent_service = None
tool_executor = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialização e limpeza da aplicação"""
    global openai_service, agent_service, tool_executor
    
    print("=" * 60)
    print("🚀 [MAIN] INICIANDO ALEEN IA - ARQUITETURA REFATORADA")
    print("=" * 60)
    print("🏗️ [MAIN] Fase 1: Design Patterns Implementation")
    print("📁 [MAIN] Estrutura modular carregando...")
    
    # Inicializa serviços
    try:
        print("\n🔧 [MAIN] Inicializando serviços...")
        
        # Verifica saúde do Supabase
        print("📊 [MAIN] Verificando Supabase...")
        health = supabase_service.health_check()
        if health["status"] != "healthy":
            print(f"❌ [MAIN] Supabase falhou: {health}")
            raise Exception(f"Supabase não está saudável: {health}")
        
        # Inicializa outros serviços
        print("🤖 [MAIN] Inicializando OpenAI Service...")
        openai_service = create_openai_service()
        
        print("👥 [MAIN] Inicializando Agent Service...")
        agent_service = create_agent_service(openai_service)
        
        print("🔧 [MAIN] Inicializando Tool Executor...")
        tool_executor = create_tool_executor()
        
        print("🌐 [MAIN] Configurando rotas da API...")
        # As rotas já estão incluídas via router, apenas logamos
        
        print("\n" + "=" * 60)
        print("✅ [MAIN] TODOS OS SERVIÇOS INICIALIZADOS COM SUCESSO!")
        print(f"� [MAIN] Ferramentas disponíveis: {len(tool_executor.tools_registry)}")
        print(f"🏥 [MAIN] Status Supabase: {health['status']}")
        print("🎯 [MAIN] Sistema pronto para receber requisições")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ [MAIN] ERRO CRÍTICO NA INICIALIZAÇÃO: {str(e)}")
        print("🛑 [MAIN] Sistema não pode continuar")
        raise
    
    yield
    
    # Limpeza
    print("\n🛑 [MAIN] Encerrando aplicação...")
    print("👋 [MAIN] Aleen IA encerrada com sucesso")

# Cria aplicação FastAPI
app = FastAPI(
    title="Aleen IA - Refactored",
    description="Sistema de IA para nutrição e fitness - Arquitetura Modular",
    version="2.0.0",
    lifespan=lifespan
)

# Inclui rotas organizadas
# Incluir as rotas organizadas
app.include_router(router)

# Endpoint de chat principal para compatibilidade
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Endpoint principal de chat - mantém compatibilidade total"""
    print(f"💬 [CHAT] Nova mensagem de {request.phone}")
    print(f"📝 [CHAT] Conteúdo: {request.message[:100]}...")
    
    try:
        # Usar os serviços refatorados para processar o chat
        if not agent_service or not tool_executor:
            raise HTTPException(status_code=503, detail="Serviços não inicializados")
        
        # Recuperar contexto do usuário
        user_context = context_manager.get_context(request.phone)
        
        # Processar mensagem com agent_service
        response_data = await agent_service.process_message(
            message=request.message,
            phone=request.phone,
            context=user_context,
            tool_executor=tool_executor
        )
        
        # Salvar contexto atualizado
        if response_data.get('updated_context'):
            context_manager.save_context(request.phone, response_data['updated_context'])
        
        response = {
            "status": "processed",
            "phone": request.phone,
            "response": response_data.get('response', 'Mensagem processada'),
            "timestamp": response_data.get('timestamp', '2025-08-29T15:52:10Z')
        }
        
        print(f"✅ [CHAT] Resposta gerada para {request.phone}")
        logger.log_info("chat_endpoint", f"Chat processado para {request.phone}")
        
        return response
        
    except Exception as e:
        print(f"❌ [CHAT] Erro no processamento: {str(e)}")
        logger.log_error("chat_endpoint", str(e), {"phone": request.phone})
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Webhook principal - processamento completo com arquitetura refatorada"""
    try:
        # Processa request
        body = await request.body()
        data = await request.json() if body else {}
        
        print(f"📨 [WEBHOOK] Requisição recebida: {data}")
        
        # Extrair dados da mensagem (formato WhatsApp/Webhook padrão)
        phone = data.get('phone', data.get('from', 'unknown'))
        message = data.get('message', data.get('text', ''))
        
        if not phone or not message:
            return {"status": "ignored", "reason": "Dados insuficientes"}
        
        # Processar usando os serviços refatorados
        if not agent_service or not tool_executor:
            raise HTTPException(status_code=503, detail="Serviços não inicializados")
        
        # Recuperar contexto
        user_context = context_manager.get_context(phone)
        
        # Processar com agent service
        response_data = await agent_service.process_message(
            message=message,
            phone=phone,
            context=user_context,
            tool_executor=tool_executor
        )
        
        # Salvar contexto
        if response_data.get('updated_context'):
            context_manager.save_context(phone, response_data['updated_context'])
        
        print(f"✅ [WEBHOOK] Processado para {phone}")
        logger.log_info("webhook_handler", f"Webhook processado para {phone}")
        
        return {
            "status": "processed",
            "phone": phone,
            "response": response_data.get('response', 'Processado'),
            "timestamp": response_data.get('timestamp')
        }
        
    except Exception as e:
        print(f"❌ [WEBHOOK] Erro: {str(e)}")
        logger.log_error("webhook_handler", str(e), {"body": str(body)[:200]})
        return {"status": "error", "error": str(e)}

@app.get("/")
async def root():
    """Endpoint de saúde básico"""
    return {
        "status": "healthy",
        "message": "Aleen IA - Arquitetura Refatorada",
        "version": "2.0.0",
        "architecture": "Design Patterns - Fase 1",
        "note": "Use /health para status detalhado"
    }

# Remove endpoints duplicados - agora estão em routes.py
# Os endpoints /health, /tools, /test_tool, /webhook, /chat estão organizados em src/api/routes.py

if __name__ == "__main__":
    # Configuração de desenvolvimento
    print("🔧 Iniciando em modo de desenvolvimento...")
    print("🏗️ Arquitetura: Design Patterns (Fase 1)")
    print("📁 Estrutura modular implementada")
    
    uvicorn.run(
        "main_refactored:app",
        host="0.0.0.0", 
        port=9000,
        reload=True,
        log_level="info"
    )

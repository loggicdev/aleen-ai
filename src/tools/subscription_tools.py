"""
Subscription Tools
Ferramentas para gerenciar assinaturas no sistema de AI
"""
from typing import Dict, Any

# Initialize services (will be set by main application)
subscription_service = None
payment_middleware = None

def set_subscription_services(sub_service=None, pay_middleware=None):
    """Set subscription services for tools to use"""
    global subscription_service, payment_middleware
    subscription_service = sub_service
    payment_middleware = pay_middleware

async def create_user_subscription_tool(
    user_id: str,
    email: str, 
    name: str,
    phone: str = None
) -> Dict[str, Any]:
    """
    Tool para criar assinatura de usuário após onboarding
    """
    try:
        if not subscription_service:
            return {
                "success": False,
                "error": "Subscription service not available",
                "message": "Sistema de assinaturas temporariamente indisponível"
            }
        
        print(f"🔧 TOOL: Criando assinatura para usuário {user_id}")
        
        result = await subscription_service.create_user_subscription(
            user_id=user_id,
            email=email,
            name=name,
            phone=phone
        )
        
        if result.get("success"):
            trial_end = result.get("trial_end", "")
            return {
                "success": True,
                "subscription_id": result.get("subscription_id"),
                "trial_end": trial_end,
                "message": f"""
🎉 *Assinatura Criada com Sucesso!*

✅ Seu período de teste gratuito de 14 dias começou agora!

📅 *Teste gratuito até:* {trial_end[:10] if trial_end else "14 dias"}

💪 *O que você pode fazer:*
• Criar planos de treino personalizados
• Receber planos de nutrição detalhados
• Acompanhar seu progresso
• Acesso completo à Aleen IA

🔄 Após o período de teste, sua assinatura será automaticamente ativada por apenas R$ 29,90/mês.

Vamos começar sua transformação! 🚀
                """.strip()
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "message": "Erro ao criar assinatura. Tente novamente ou entre em contato com o suporte."
            }
            
    except Exception as e:
        print(f"❌ Error in create_user_subscription_tool: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Erro interno ao criar assinatura. Entre em contato com o suporte."
        }

async def check_user_subscription_access_tool(user_id: str) -> Dict[str, Any]:
    """
    Tool para verificar se usuário tem acesso baseado na assinatura
    """
    try:
        if not payment_middleware:
            # Development mode - allow access
            return {
                "has_access": True,
                "status": "development",
                "message": "Modo desenvolvimento - acesso liberado"
            }
        
        print(f"🔧 TOOL: Verificando acesso para usuário {user_id}")
        
        access_check = await payment_middleware.require_subscription(user_id)
        
        if access_check.get("access_denied"):
            return {
                "has_access": False,
                "status": access_check["subscription_info"].get("status", "unknown"),
                "message": access_check.get("message", "Acesso negado"),
                "subscription_info": access_check["subscription_info"]
            }
        else:
            return {
                "has_access": True,
                "status": access_check["subscription_info"].get("status", "active"),
                "subscription_info": access_check["subscription_info"]
            }
            
    except Exception as e:
        print(f"❌ Error in check_user_subscription_access_tool: {e}")
        # Default to allowing access to not break existing functionality
        return {
            "has_access": True,
            "status": "error",
            "message": f"Erro ao verificar assinatura: {str(e)}"
        }

# Tool definitions for OpenAI integration
SUBSCRIPTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_user_subscription",
            "description": "Cria assinatura de 14 dias de trial gratuito para usuário após completar onboarding. Use quando o usuário completar o cadastro e quiser começar a usar os recursos premium.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "ID do usuário no sistema"
                    },
                    "email": {
                        "type": "string",
                        "description": "Email do usuário"
                    },
                    "name": {
                        "type": "string", 
                        "description": "Nome completo do usuário"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Telefone do usuário (opcional)"
                    }
                },
                "required": ["user_id", "email", "name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_user_subscription_access",
            "description": "Verifica se o usuário tem acesso aos recursos premium baseado no status da assinatura. Use antes de executar outras ferramentas que requerem assinatura ativa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "ID do usuário no sistema"
                    }
                },
                "required": ["user_id"]
            }
        }
    }
]

"""
Payment Middleware
Verifica acesso do usuário baseado no status da assinatura
"""
from typing import Dict, Any, Optional
from functools import wraps

class PaymentMiddleware:
    def __init__(self, subscription_service=None):
        """Initialize with subscription service"""
        self.subscription_service = subscription_service
        print("✅ PaymentMiddleware initialized")
    
    async def check_user_access(self, user_id: str) -> Dict[str, Any]:
        """
        Verifica se o usuário tem acesso baseado na assinatura
        Returns: {"has_access": bool, "reason": str, "subscription_info": dict}
        """
        try:
            if not self.subscription_service:
                # Development mode - allow all access
                return {
                    "has_access": True,
                    "reason": "Development mode - subscription service not available",
                    "subscription_info": {}
                }
            
            # Check subscription status
            subscription_status = await self.subscription_service.check_user_subscription_status(user_id)
            
            return {
                "has_access": subscription_status.get("has_access", False),
                "reason": subscription_status.get("reason", "Unknown"),
                "subscription_info": subscription_status
            }
            
        except Exception as e:
            print(f"❌ Error checking user access: {e}")
            # Default to allowing access to not break existing functionality
            return {
                "has_access": True,
                "reason": f"Error in access check: {str(e)}",
                "subscription_info": {}
            }
    
    def get_access_denied_message(self, subscription_info: Dict) -> str:
        """
        Generate appropriate message for access denial
        """
        status = subscription_info.get("status", "unknown")
        
        if status == "no_subscription":
            return """
🚫 *Acesso Negado*

Para continuar usando a Aleen IA, você precisa ativar sua assinatura.

💳 *Como ativar:*
1. Acesse seu painel de usuário
2. Complete o processo de assinatura
3. Aproveite todos os recursos da Aleen!

✨ *Benefícios da assinatura:*
• Planos de treino personalizados
• Planos de nutrição detalhados  
• Acompanhamento de progresso
• Suporte 24/7 da Aleen IA

Entre em contato se precisar de ajuda! 💪
            """.strip()
        
        elif status == "trial_expired":
            trial_end = subscription_info.get("trial_end", "")
            return f"""
⏰ *Trial Expirado*

Seu período de teste gratuito de 14 dias terminou em {trial_end[:10]}.

💳 *Para continuar:*
1. Ative sua assinatura mensal
2. Continue aproveitando todos os recursos
3. Sem interrupções no seu progresso!

✨ *Não perca seu progresso:*
• Seus dados estão salvos
• Planos personalizados esperando
• Continue de onde parou

Ative agora e continue sua jornada! 🚀
            """.strip()
        
        elif status == "canceled":
            return """
💔 *Assinatura Cancelada*

Sua assinatura foi cancelada e você perdeu o acesso aos recursos premium.

🔄 *Quer voltar?*
1. Reative sua assinatura
2. Recupere todos seus dados
3. Continue sua evolução!

Sentimos sua falta! Volte quando quiser! 💪
            """.strip()
        
        elif status == "past_due":
            return """
⚠️ *Pagamento Pendente*

Sua assinatura está com pagamento em atraso.

💳 *Para resolver:*
1. Atualize seu método de pagamento
2. Quite as pendências
3. Recupere o acesso imediatamente

Não queremos te ver parado! Resolva rapidinho! ⚡
            """.strip()
        
        else:
            return """
🚫 *Acesso Temporariamente Indisponível*

Estamos verificando o status da sua assinatura.

🔄 Tente novamente em alguns minutos ou entre em contato se o problema persistir.
            """.strip()
    
    async def require_subscription(self, user_id: str) -> Dict[str, Any]:
        """
        Decorator helper - check subscription and return appropriate response
        """
        access_check = await self.check_user_access(user_id)
        
        if not access_check["has_access"]:
            denial_message = self.get_access_denied_message(access_check["subscription_info"])
            return {
                "access_denied": True,
                "message": denial_message,
                "subscription_info": access_check["subscription_info"]
            }
        
        return {
            "access_denied": False,
            "subscription_info": access_check["subscription_info"]
        }

# Utility function for easy middleware checking
async def check_subscription_access(user_id: str, subscription_service=None) -> Dict[str, Any]:
    """
    Standalone function to check subscription access
    Can be used without instantiating the class
    """
    middleware = PaymentMiddleware(subscription_service)
    return await middleware.require_subscription(user_id)

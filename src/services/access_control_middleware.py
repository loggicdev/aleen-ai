"""
Access Control Middleware
Middleware para verificar assinatura e bloquear acesso quando necessário
"""
import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AccessControlMiddleware:
    def __init__(self, subscription_checker=None, checkout_service=None):
        """Initialize with required services"""
        self.subscription_checker = subscription_checker
        self.checkout_service = checkout_service
        logger.info("🛡️ AccessControlMiddleware initialized")
    
    async def check_subscription_access(self, user_id: str) -> Dict[str, Any]:
        """
        Verifica acesso do usuário e retorna resultado detalhado
        """
        try:
            logger.info(f"🔐 Checking access for user: {user_id}")
            
            if not self.subscription_checker:
                logger.error("❌ Subscription checker not available")
                raise HTTPException(
                    status_code=503,
                    detail="Subscription service unavailable"
                )
            
            # Verificar acesso
            access_result = await self.subscription_checker.check_user_subscription_access(user_id)
            logger.info(f"📊 Access check result: {access_result}")
            
            # Se tem acesso, retornar sucesso
            if access_result.get("access_allowed"):
                logger.info(f"✅ Access granted for user {user_id}")
                return {
                    "access_granted": True,
                    "subscription_status": access_result.get("subscription_status"),
                    "subscription_data": access_result.get("subscription_data")
                }
            
            # Se não tem acesso, precisa criar checkout
            logger.warning(f"🚫 Access denied for user {user_id} - creating checkout")
            
            # Buscar dados do usuário
            user_profile = await self.subscription_checker.get_user_profile_for_subscription(user_id)
            
            if user_profile.get("error"):
                logger.error(f"❌ Failed to get user profile: {user_profile['error']}")
                
                # Se faltam campos, informar quais são necessários
                if "missing_fields" in user_profile:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "user_profile_incomplete",
                            "message": "Perfil do usuário incompleto para criar assinatura",
                            "missing_fields": user_profile["missing_fields"],
                            "current_data": user_profile.get("user_data")
                        }
                    )
                
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "user_not_found",
                        "message": "Usuário não encontrado"
                    }
                )
            
            user_data = user_profile["user_data"]
            
            # Criar checkout session
            if not self.checkout_service:
                logger.error("❌ Checkout service not available")
                raise HTTPException(
                    status_code=503,
                    detail="Checkout service unavailable"
                )
            
            checkout_result = await self.checkout_service.create_subscription_checkout(
                user_id=user_data["id"],
                user_email=user_data["email"],
                user_name=user_data["name"]
            )
            
            if checkout_result.get("error"):
                logger.error(f"❌ Failed to create checkout: {checkout_result['error']}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "checkout_creation_failed",
                        "message": "Falha ao criar link de pagamento",
                        "details": checkout_result.get("details")
                    }
                )
            
            logger.info(f"💳 Checkout created successfully for user {user_id}")
            
            # Retornar informações para bloqueio + checkout
            raise HTTPException(
                status_code=402,  # Payment Required
                detail={
                    "error": "subscription_required",
                    "message": "Assinatura necessária para acessar este recurso",
                    "subscription_status": access_result.get("subscription_status"),
                    "checkout_url": checkout_result["checkout_url"],
                    "plan_info": checkout_result.get("plan_info"),
                    "trial_available": True
                }
            )
            
        except HTTPException:
            # Re-raise HTTPExceptions
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error in access control: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "internal_error",
                    "message": "Erro interno no controle de acesso"
                }
            )
    
    async def require_active_subscription(self, user_id: str) -> Dict[str, Any]:
        """
        Decorator/function para exigir assinatura ativa
        Retorna dados da assinatura se válida, senão levanta exceção
        """
        return await self.check_subscription_access(user_id)

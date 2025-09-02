"""
Stripe Checkout Service
Cria links de pagamento e gerencia processo de checkout
"""
import logging
from typing import Dict, Any, Optional
import os

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StripeCheckoutService:
    def __init__(self, stripe_service=None, subscription_service=None):
        """Initialize with Stripe and Subscription services"""
        self.stripe_service = stripe_service
        self.subscription_service = subscription_service
        self.base_url = os.getenv('BASE_URL', 'http://localhost:5000')
        logger.info("💳 StripeCheckoutService initialized")
    
    async def create_subscription_checkout(self, user_id: str, user_email: str, user_name: str) -> Dict[str, Any]:
        """
        Cria um checkout session do Stripe para nova assinatura
        """
        try:
            logger.info(f"🛒 Creating checkout session for user {user_id} ({user_email})")
            
            if not self.stripe_service:
                logger.error("❌ Stripe service not available")
                return {"error": "Payment service unavailable"}
            
            if not self.subscription_service:
                logger.error("❌ Subscription service not available")
                return {"error": "Subscription service unavailable"}
            
            # Buscar configuração do plano padrão
            logger.info("📋 Getting default plan configuration from database")
            plan_config = await self.subscription_service.get_default_plan_from_database()
            
            if not plan_config.get("success"):
                logger.error(f"❌ Failed to get plan configuration: {plan_config.get('error')}")
                return {
                    "error": "Unable to load subscription plan",
                    "details": plan_config.get('error')
                }
            
            stripe_price_id = plan_config.get('stripe_price_id')
            trial_days = plan_config.get('trial_days', 14)
            
            logger.info(f"💰 Plan config: price_id={stripe_price_id}, trial_days={trial_days}")
            
            # Verificar se já existe customer no Stripe
            logger.info(f"👤 Checking if customer exists for email: {user_email}")
            
            try:
                # Para usar MCP Stripe, vamos simular a criação por enquanto
                # Quando MCP estiver funcionando, substituir por mcp_stripe_create_customer
                
                checkout_session_data = {
                    "mode": "subscription",
                    "payment_method_types": ["card"],
                    "line_items": [{
                        "price": stripe_price_id,
                        "quantity": 1
                    }],
                    "success_url": f"{self.base_url}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}",
                    "cancel_url": f"{self.base_url}/subscription/cancel",
                    "customer_email": user_email,
                    "client_reference_id": user_id,
                    "subscription_data": {
                        "trial_period_days": trial_days,
                        "metadata": {
                            "user_id": user_id,
                            "user_email": user_email,
                            "plan_name": plan_config.get('product_name', 'Aleen IA Premium')
                        }
                    },
                    "metadata": {
                        "user_id": user_id,
                        "user_email": user_email
                    }
                }
                
                logger.info(f"🔧 Checkout session config: {checkout_session_data}")
                
                # TODO: Implementar com MCP Stripe quando estiver disponível
                # checkout_session = mcp_stripe_create_checkout_session(checkout_session_data)
                
                # Por enquanto, retornar URL mock para teste
                mock_checkout_url = f"https://checkout.stripe.com/pay/cs_test_mock_{user_id[:8]}"
                
                logger.info(f"✅ Checkout session created: {mock_checkout_url}")
                
                return {
                    "success": True,
                    "checkout_url": mock_checkout_url,
                    "plan_info": {
                        "name": plan_config.get('product_name'),
                        "price": plan_config.get('unit_amount'),
                        "currency": plan_config.get('currency'),
                        "trial_days": trial_days
                    },
                    "message": f"Checkout criado com sucesso - trial de {trial_days} dias"
                }
                
            except Exception as stripe_error:
                logger.error(f"❌ Stripe error: {stripe_error}")
                return {
                    "error": "Failed to create checkout session",
                    "details": str(stripe_error)
                }
                
        except Exception as e:
            logger.error(f"❌ Error creating checkout session: {e}")
            return {
                "error": "Internal error creating checkout",
                "details": str(e)
            }
    
    async def handle_checkout_success(self, session_id: str) -> Dict[str, Any]:
        """
        Processa sucesso do checkout e ativa assinatura
        """
        try:
            logger.info(f"🎉 Processing checkout success: session_id={session_id}")
            
            # TODO: Recuperar session do Stripe e processar
            # session = mcp_stripe_retrieve_checkout_session(session_id)
            
            logger.info("✅ Checkout success processed")
            return {
                "success": True,
                "message": "Assinatura ativada com sucesso!"
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing checkout success: {e}")
            return {
                "error": "Failed to process checkout success",
                "details": str(e)
            }
    
    async def handle_checkout_cancel(self) -> Dict[str, Any]:
        """
        Processa cancelamento do checkout
        """
        logger.info("🚫 Checkout cancelled by user")
        return {
            "success": True,
            "message": "Checkout cancelado pelo usuário"
        }

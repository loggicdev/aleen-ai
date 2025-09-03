"""
Stripe Webhook Handler
Processa eventos do Stripe para atualizar assinaturas
"""
import logging
from typing import Dict, Any
from datetime import datetime, timedelta, timedelta

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StripeWebhookHandler:
    def __init__(self, supabase_service=None):
        """Initialize with Supabase service"""
        self.supabase = supabase_service
        logger.info("📨 StripeWebhookHandler initialized")
    
    async def handle_checkout_session_completed(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa evento checkout.session.completed
        Cria subscription após pagamento bem-sucedido
        """
        try:
            session = event_data.get('data', {}).get('object', {})
            session_id = session.get('id')
            customer_id = session.get('customer')
            subscription_id = session.get('subscription')
            user_id = session.get('metadata', {}).get('user_id')
            
            logger.info(f"📨 Processando checkout completo: session={session_id}, user={user_id}")
            
            if not all([session_id, customer_id, subscription_id, user_id]):
                logger.error(f"❌ Dados incompletos no webhook: session={session_id}, customer={customer_id}, sub={subscription_id}, user={user_id}")
                return {"error": "Incomplete webhook data"}
            
            # Buscar detalhes da subscription no Stripe
            # TODO: Implementar com MCP Stripe quando disponível
            # subscription_details = mcp_stripe_fetch_subscription(subscription_id)
            
            # Por enquanto, criar com dados básicos
            # Buscar product_id e price_id do banco baseado no plano ativo
            plan_data = self.supabase.client.table('prices')\
                .select('id, product_id, stripe_price_id, trial_period_days')\
                .eq('is_active', True)\
                .limit(1)\
                .execute()
            
            if not plan_data.data:
                logger.error("❌ Nenhum plano ativo encontrado no banco")
                return {"error": "No active plan found"}
            
            plan = plan_data.data[0]
            
            # Criar registro de subscription
            now = datetime.utcnow()
            trial_days = plan.get('trial_period_days', 14)  # Default 14 dias
            trial_end = now + timedelta(days=trial_days)
            period_end = trial_end  # O período pago começa após o trial
            
            subscription_data = {
                'user_id': user_id,
                'product_id': plan['product_id'],
                'price_id': plan['id'],
                'stripe_subscription_id': subscription_id,
                'status': 'trialing',
                'trial_start': now.isoformat(),
                'trial_end': trial_end.isoformat(),
                'current_period_start': now.isoformat(),
                'current_period_end': period_end.isoformat(),
                'cancel_at_period_end': False,
                'created_at': now.isoformat(),
                'updated_at': now.isoformat()
            }
            
            # Inserir subscription
            subscription_result = self.supabase.client.table('subscriptions')\
                .insert(subscription_data)\
                .execute()
            
            if subscription_result.data:
                logger.info(f"✅ Subscription criada: {subscription_id}")
                
                # Atualizar checkout session para completed
                checkout_update = self.supabase.client.table('checkout_sessions')\
                    .update({
                        'status': 'completed',
                        'completed_at': datetime.utcnow().isoformat()
                    })\
                    .eq('stripe_checkout_session_id', session_id)\
                    .execute()
                
                logger.info(f"✅ Checkout session atualizada: {session_id}")
                
                return {
                    "success": True,
                    "subscription_id": subscription_id,
                    "user_id": user_id,
                    "status": "trialing"
                }
            else:
                logger.error(f"❌ Falha ao criar subscription: {subscription_result}")
                return {"error": "Failed to create subscription"}
                
        except Exception as e:
            logger.error(f"❌ Erro processando webhook: {e}")
            return {"error": str(e)}
    
    async def handle_subscription_updated(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa evento customer.subscription.updated
        Atualiza status da subscription (trial -> active, cancelamento, etc.)
        """
        try:
            subscription = event_data.get('data', {}).get('object', {})
            subscription_id = subscription.get('id')
            status = subscription.get('status')
            
            logger.info(f"📨 Atualizando subscription: {subscription_id} -> {status}")
            
            # Atualizar no banco
            update_result = self.supabase.client.table('subscriptions')\
                .update({
                    'status': status,
                    'updated_at': datetime.utcnow().isoformat()
                })\
                .eq('stripe_subscription_id', subscription_id)\
                .execute()
            
            if update_result.data:
                logger.info(f"✅ Subscription atualizada: {subscription_id} -> {status}")
                return {"success": True, "subscription_id": subscription_id, "new_status": status}
            else:
                logger.error(f"❌ Subscription não encontrada: {subscription_id}")
                return {"error": "Subscription not found"}
                
        except Exception as e:
            logger.error(f"❌ Erro atualizando subscription: {e}")
            return {"error": str(e)}
    
    async def process_webhook_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa evento do webhook baseado no tipo
        """
        try:
            event_type = event.get('type')
            logger.info(f"📨 Webhook recebido: {event_type}")
            
            if event_type == 'checkout.session.completed':
                return await self.handle_checkout_session_completed(event)
            elif event_type == 'customer.subscription.updated':
                return await self.handle_subscription_updated(event)
            elif event_type == 'customer.subscription.deleted':
                return await self.handle_subscription_updated(event)  # Mesmo handler
            else:
                logger.info(f"⚠️ Evento não tratado: {event_type}")
                return {"success": True, "message": f"Event {event_type} ignored"}
                
        except Exception as e:
            logger.error(f"❌ Erro processando webhook event: {e}")
            return {"error": str(e)}

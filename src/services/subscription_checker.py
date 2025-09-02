"""
Subscription Checker Service
Verifica status de assinatura do usuário e bloqueia acesso quando necessário
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SubscriptionChecker:
    def __init__(self, supabase_service=None):
        """Initialize with Supabase service"""
        self.supabase = supabase_service
        logger.info("🔐 SubscriptionChecker initialized")
    
    async def check_user_subscription_access(self, user_id: str) -> Dict[str, Any]:
        """
        Verifica se o usuário tem acesso ao sistema baseado na assinatura
        
        Retorna:
        - access_allowed: bool
        - subscription_status: str
        - requires_payment: bool
        - trial_expired: bool
        - checkout_url: str (se necessário)
        """
        try:
            logger.info(f"🔍 Checking subscription access for user {user_id}")
            
            if not self.supabase:
                logger.error("❌ Supabase service not available")
                return {
                    "access_allowed": False,
                    "error": "Database service unavailable",
                    "requires_payment": True
                }
            
            # Buscar assinatura ativa do usuário
            subscription_result = self.supabase.table('subscriptions')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            logger.info(f"📊 Subscription query result: {len(subscription_result.data) if subscription_result.data else 0} records found")
            
            # Se não tem assinatura, precisa criar
            if not subscription_result.data or len(subscription_result.data) == 0:
                logger.warning(f"⚠️ No subscription found for user {user_id}")
                return {
                    "access_allowed": False,
                    "subscription_status": "no_subscription",
                    "requires_payment": True,
                    "trial_expired": False,
                    "message": "Usuário não possui assinatura ativa"
                }
            
            subscription = subscription_result.data[0]
            logger.info(f"🎯 Found subscription: status={subscription.get('status')}, stripe_id={subscription.get('stripe_subscription_id')}")
            
            # Verificar status da assinatura
            status = subscription.get('status', '').lower()
            trial_end = subscription.get('trial_end')
            current_period_end = subscription.get('current_period_end')
            
            # Log detalhado do status
            logger.info(f"📅 Subscription details: status={status}, trial_end={trial_end}, current_period_end={current_period_end}")
            
            # Status que permitem acesso
            active_statuses = ['active', 'trialing']
            
            if status in active_statuses:
                # Verificar se trial expirou
                if status == 'trialing' and trial_end:
                    trial_end_date = datetime.fromisoformat(trial_end.replace('Z', '+00:00'))
                    if datetime.now(trial_end_date.tzinfo) > trial_end_date:
                        logger.warning(f"⏰ Trial expired for user {user_id}")
                        return {
                            "access_allowed": False,
                            "subscription_status": "trial_expired",
                            "requires_payment": True,
                            "trial_expired": True,
                            "message": "Período de teste expirado"
                        }
                
                logger.info(f"✅ Access granted for user {user_id} - status: {status}")
                return {
                    "access_allowed": True,
                    "subscription_status": status,
                    "requires_payment": False,
                    "trial_expired": False,
                    "subscription_data": subscription
                }
            
            # Status que requerem pagamento
            logger.warning(f"🚫 Access denied for user {user_id} - status: {status}")
            return {
                "access_allowed": False,
                "subscription_status": status,
                "requires_payment": True,
                "trial_expired": status == 'past_due',
                "message": f"Assinatura {status} - pagamento necessário"
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking subscription access for user {user_id}: {e}")
            return {
                "access_allowed": False,
                "error": str(e),
                "requires_payment": True
            }
    
    async def get_user_profile_for_subscription(self, user_id: str) -> Dict[str, Any]:
        """
        Busca dados do usuário necessários para criação de assinatura
        """
        try:
            logger.info(f"👤 Getting user profile for subscription: {user_id}")
            
            if not self.supabase:
                logger.error("❌ Supabase service not available")
                return {"error": "Database service unavailable"}
            
            # Buscar dados do usuário
            user_result = self.supabase.table('users')\
                .select('id, email, name, phone')\
                .eq('id', user_id)\
                .single()\
                .execute()
            
            if not user_result.data:
                logger.error(f"❌ User not found: {user_id}")
                return {"error": "User not found"}
            
            user = user_result.data
            logger.info(f"✅ User profile retrieved: email={user.get('email')}, name={user.get('name')}")
            
            # Verificar campos obrigatórios
            missing_fields = []
            if not user.get('email'):
                missing_fields.append('email')
            if not user.get('name'):
                missing_fields.append('name')
            
            if missing_fields:
                logger.warning(f"⚠️ Missing required fields for user {user_id}: {missing_fields}")
                return {
                    "error": "Missing required fields",
                    "missing_fields": missing_fields,
                    "user_data": user
                }
            
            return {
                "success": True,
                "user_data": {
                    "id": user['id'],
                    "email": user['email'],
                    "name": user['name'],
                    "phone": user.get('phone')
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting user profile: {e}")
            return {"error": str(e)}

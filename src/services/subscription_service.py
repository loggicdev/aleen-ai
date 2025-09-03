"""
Subscription Service
Gerencia lógica de assinaturas e integração com banco de dados
"""
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

# Import do Supabase service existente
try:
    from src.services.supabase_service import supabase_service
except ImportError:
    try:
        from services.supabase_service import supabase_service
    except ImportError:
        print("⚠️ Supabase service não disponível")
        supabase_service = None

class SubscriptionService:
    def __init__(self, stripe_service=None):
        """Initialize with Stripe and Supabase services"""
        self.stripe_service = stripe_service
        self.supabase = supabase_service
        
        # NO MORE HARDCODED VALUES - Everything comes from database
        print("✅ SubscriptionService initialized - all data will come from database")
    
    async def get_default_plan_from_database(self) -> Dict[str, Any]:
        """
        Busca o plano padrão ativo do banco de dados
        """
        try:
            if not self.supabase:
                return {"error": "Database not available"}
            
            # Buscar primeiro produto ativo com preço ativo
            result = self.supabase.client.table('products')\
                .select('''
                    id,
                    stripe_product_id,
                    name,
                    prices!inner (
                        stripe_price_id,
                        unit_amount,
                        currency,
                        interval_type,
                        trial_period_days
                    )
                ''')\
                .eq('is_active', True)\
                .eq('prices.is_active', True)\
                .limit(1)\
                .execute()
            
            if result.data and len(result.data) > 0:
                product = result.data[0]
                price = product['prices'][0]  # Primeiro preço ativo
                
                return {
                    "success": True,
                    "product_id": product['id'],
                    "stripe_product_id": product['stripe_product_id'],
                    "product_name": product['name'],
                    "stripe_price_id": price['stripe_price_id'],
                    "unit_amount": price['unit_amount'],
                    "currency": price['currency'],
                    "interval": price['interval_type'],
                    "trial_days": price['trial_period_days']
                }
            else:
                return {"error": "No active subscription plan found in database"}
                
        except Exception as e:
            print(f"❌ Error getting default plan from database: {e}")
            return {"error": str(e)}

    async def create_user_subscription(
        self, 
        user_id: str, 
        email: str, 
        name: str, 
        phone: str = None
    ) -> Dict[str, Any]:
        """
        Complete subscription creation flow:
        1. Create Stripe customer
        2. Create Stripe subscription with trial
        3. Save subscription data in database
        """
        try:
            print(f"🚀 Creating subscription for user {user_id} ({email})")
            
            # STEP 0: Get plan configuration from database
            plan_config = await self.get_default_plan_from_database()
            if not plan_config.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to get plan configuration: {plan_config.get('error')}"
                }
            
            print(f"📋 Using plan from database: {plan_config['product_name']} - {plan_config['stripe_price_id']}")
            print(f"💰 Price: {plan_config['unit_amount']/100} {plan_config['currency'].upper()}")
            print(f"🆓 Trial: {plan_config['trial_days']} days")
            
            # Step 1: Create Stripe customer
            if self.stripe_service:
                customer_result = await self.stripe_service.create_customer(email, name, phone)
                if not customer_result.get('success'):
                    return {
                        "success": False,
                        "error": f"Failed to create Stripe customer: {customer_result.get('error')}"
                    }
                
                customer_id = customer_result['customer_id']
                print(f"✅ Stripe customer created: {customer_id}")
            else:
                # Mock for development
                customer_id = f"cus_mock_{user_id[:8]}"
                print(f"🔧 Mock Stripe customer: {customer_id}")
            
            # Step 2: Create Stripe subscription
            if self.stripe_service:
                subscription_result = await self.stripe_service.create_subscription(
                    customer_id, 
                    plan_config['stripe_price_id'],  # From database
                    plan_config['trial_days']        # From database
                )
                if not subscription_result.get('success'):
                    return {
                        "success": False,
                        "error": f"Failed to create Stripe subscription: {subscription_result.get('error')}"
                    }
                
                subscription = subscription_result['subscription']
                subscription_id = subscription['id']
            else:
                # Mock for development
                trial_end = datetime.now() + timedelta(days=plan_config['trial_days'])
                subscription = {
                    "id": f"sub_mock_{user_id[:8]}",
                    "customer": customer_id,
                    "status": "trialing",
                    "trial_start": datetime.now().timestamp(),
                    "trial_end": trial_end.timestamp(),
                    "current_period_start": datetime.now().timestamp(),
                    "current_period_end": trial_end.timestamp()
                }
                subscription_id = subscription['id']
                print(f"🔧 Mock Stripe subscription: {subscription_id}")
            
            # Step 3: Save to database
            trial_start = datetime.fromtimestamp(subscription['trial_start'])
            trial_end = datetime.fromtimestamp(subscription['trial_end'])
            period_start = datetime.fromtimestamp(subscription['current_period_start'])
            period_end = datetime.fromtimestamp(subscription['current_period_end'])
            
            subscription_data = {
                "user_id": user_id,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "stripe_price_id": plan_config['stripe_price_id'],  # From database
                "status": subscription['status'],
                "trial_start": trial_start.isoformat(),
                "trial_end": trial_end.isoformat(),
                "current_period_start": period_start.isoformat(),
                "current_period_end": period_end.isoformat()
            }
            
            if self.supabase:
                db_result = self.supabase.client.table('subscriptions').insert(subscription_data).execute()
                if not db_result.data:
                    print(f"⚠️ Failed to save subscription to database")
                    # Continue anyway, subscription was created in Stripe
                else:
                    print(f"✅ Subscription saved to database")
            
            return {
                "success": True,
                "subscription_id": subscription_id,
                "customer_id": customer_id,
                "trial_end": trial_end.isoformat(),
                "status": subscription['status']
            }
            
        except Exception as e:
            print(f"❌ Error creating user subscription: {e}")
            return {"success": False, "error": str(e)}
    
    async def check_user_subscription_status(self, user_id: str) -> Dict[str, Any]:
        """
        Check if user has active subscription
        Returns access permission and subscription details
        """
        try:
            if not self.supabase:
                # Development fallback - allow access
                return {
                    "has_access": True,
                    "status": "active",
                    "reason": "Development mode - Supabase not available"
                }
            
            # Get subscription from database
            subscription_result = self.supabase.client.table('subscriptions')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if not subscription_result.data:
                return {
                    "has_access": False,
                    "status": "no_subscription",
                    "reason": "No subscription found for user"
                }
            
            subscription = subscription_result.data[0]
            current_status = subscription['status']
            
            # Check if subscription allows access
            active_statuses = ['trialing', 'active']
            has_access = current_status in active_statuses
            
            # Additional checks for trial expiration
            if current_status == 'trialing':
                trial_end = datetime.fromisoformat(subscription['trial_end'].replace('Z', '+00:00'))
                if datetime.now(trial_end.tzinfo) > trial_end:
                    has_access = False
                    current_status = 'trial_expired'
            
            return {
                "has_access": has_access,
                "status": current_status,
                "subscription": subscription,
                "trial_end": subscription.get('trial_end'),
                "current_period_end": subscription.get('current_period_end')
            }
            
        except Exception as e:
            print(f"❌ Error checking subscription status: {e}")
            # In case of error, default to allowing access to not break the system
            return {
                "has_access": True,
                "status": "error",
                "reason": f"Error checking subscription: {str(e)}"
            }
    
    async def update_subscription_status(
        self, 
        stripe_subscription_id: str, 
        new_status: str,
        webhook_data: Dict = None
    ) -> Dict[str, Any]:
        """
        Update subscription status from Stripe webhook
        """
        try:
            if not self.supabase:
                print("⚠️ Cannot update subscription - Supabase not available")
                return {"success": False, "error": "Database not available"}
            
            update_data = {"status": new_status}
            
            # Add additional data from webhook if available
            if webhook_data:
                if 'current_period_start' in webhook_data:
                    update_data['current_period_start'] = datetime.fromtimestamp(
                        webhook_data['current_period_start']
                    ).isoformat()
                
                if 'current_period_end' in webhook_data:
                    update_data['current_period_end'] = datetime.fromtimestamp(
                        webhook_data['current_period_end']
                    ).isoformat()
                
                if 'cancel_at_period_end' in webhook_data:
                    update_data['cancel_at_period_end'] = webhook_data['cancel_at_period_end']
            
            result = self.supabase.client.table('subscriptions')\
                .update(update_data)\
                .eq('stripe_subscription_id', stripe_subscription_id)\
                .execute()
            
            if result.data:
                print(f"✅ Subscription {stripe_subscription_id} updated to status: {new_status}")
                return {"success": True, "updated": result.data[0]}
            else:
                print(f"⚠️ No subscription found with ID: {stripe_subscription_id}")
                return {"success": False, "error": "Subscription not found"}
                
        except Exception as e:
            print(f"❌ Error updating subscription status: {e}")
            return {"success": False, "error": str(e)}

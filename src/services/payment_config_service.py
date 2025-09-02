"""
Payment Configuration Service
Centraliza todas as configurações de pagamento vindas do banco
"""
from typing import Dict, Any, Optional

class PaymentConfigService:
    def __init__(self, supabase_service=None):
        """Initialize with Supabase service"""
        self.supabase = supabase_service
        print("✅ PaymentConfigService initialized - NO hardcoded values")
    
    async def get_active_subscription_plans(self) -> Dict[str, Any]:
        """
        Busca todos os planos de assinatura ativos do banco
        """
        try:
            if not self.supabase:
                return {"success": False, "error": "Database not available", "plans": []}
            
            result = self.supabase.table('products')\
                .select('''
                    id,
                    stripe_product_id,
                    name,
                    description,
                    metadata,
                    prices!inner (
                        id,
                        stripe_price_id,
                        unit_amount,
                        currency,
                        interval_type,
                        interval_count,
                        trial_period_days,
                        nickname,
                        is_active
                    )
                ''')\
                .eq('is_active', True)\
                .eq('prices.is_active', True)\
                .execute()
            
            if result.data:
                plans = []
                for product in result.data:
                    for price in product['prices']:
                        plan = {
                            "product_id": product['id'],
                            "stripe_product_id": product['stripe_product_id'],
                            "stripe_price_id": price['stripe_price_id'],
                            "name": product['name'],
                            "description": product['description'],
                            "unit_amount": price['unit_amount'],
                            "currency": price['currency'],
                            "interval": price['interval_type'],
                            "interval_count": price['interval_count'],
                            "trial_days": price['trial_period_days'],
                            "nickname": price['nickname'],
                            "features": product.get('metadata', {}).get('features', [])
                        }
                        plans.append(plan)
                
                return {"success": True, "plans": plans}
            else:
                return {"success": True, "plans": []}
                
        except Exception as e:
            print(f"❌ Error getting subscription plans: {e}")
            return {"success": False, "error": str(e), "plans": []}
    
    async def get_default_plan(self) -> Dict[str, Any]:
        """
        Busca o plano padrão (primeiro ativo) do banco
        """
        try:
            plans_result = await self.get_active_subscription_plans()
            
            if plans_result.get("success") and plans_result["plans"]:
                return {"success": True, "plan": plans_result["plans"][0]}
            else:
                return {"success": False, "error": "No active plans found"}
                
        except Exception as e:
            print(f"❌ Error getting default plan: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_plan_by_price_id(self, stripe_price_id: str) -> Dict[str, Any]:
        """
        Busca plano específico por stripe_price_id
        """
        try:
            if not self.supabase:
                return {"success": False, "error": "Database not available"}
            
            result = self.supabase.table('prices')\
                .select('''
                    id,
                    stripe_price_id,
                    unit_amount,
                    currency,
                    interval_type,
                    trial_period_days,
                    products!inner (
                        id,
                        stripe_product_id,
                        name,
                        description,
                        metadata
                    )
                ''')\
                .eq('stripe_price_id', stripe_price_id)\
                .eq('is_active', True)\
                .limit(1)\
                .execute()
            
            if result.data and len(result.data) > 0:
                price_data = result.data[0]
                product_data = price_data['products']
                
                plan = {
                    "product_id": product_data['id'],
                    "stripe_product_id": product_data['stripe_product_id'],
                    "stripe_price_id": price_data['stripe_price_id'],
                    "name": product_data['name'],
                    "description": product_data['description'],
                    "unit_amount": price_data['unit_amount'],
                    "currency": price_data['currency'],
                    "interval": price_data['interval_type'],
                    "trial_days": price_data['trial_period_days'],
                    "features": product_data.get('metadata', {}).get('features', [])
                }
                
                return {"success": True, "plan": plan}
            else:
                return {"success": False, "error": f"Plan with price_id {stripe_price_id} not found"}
                
        except Exception as e:
            print(f"❌ Error getting plan by price ID: {e}")
            return {"success": False, "error": str(e)}

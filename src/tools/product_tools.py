"""
Product Tools
Ferramentas para gerenciar produtos e preços
"""
from typing import Dict, Any, List

# Initialize services (will be set by main application)
supabase_service = None

def set_product_services(supabase_svc=None):
    """Set product services for tools to use"""
    global supabase_service
    supabase_service = supabase_svc

async def get_available_subscription_plans() -> Dict[str, Any]:
    """
    Tool para buscar planos de assinatura disponíveis
    """
    try:
        if not supabase_service:
            return {
                "success": False,
                "error": "Database service not available",
                "plans": []
            }
        
        print("🔧 TOOL: Buscando planos de assinatura disponíveis")
        
        # Buscar produtos ativos com seus preços
        result = supabase_service.table('products')\
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
                    metadata
                )
            ''')\
            .eq('is_active', True)\
            .eq('prices.is_active', True)\
            .execute()
        
        if result.data:
            plans = []
            for product in result.data:
                for price in product['prices']:
                    # Format price display
                    amount = price['unit_amount'] / 100
                    currency_symbol = "$" if price['currency'] == 'usd' else price['currency'].upper()
                    
                    plan = {
                        "product_id": product['id'],
                        "stripe_product_id": product['stripe_product_id'],
                        "stripe_price_id": price['stripe_price_id'],
                        "name": product['name'],
                        "description": product['description'],
                        "price_display": f"{currency_symbol}{amount:.2f}/{price['interval_type']}",
                        "price_amount": price['unit_amount'],
                        "currency": price['currency'],
                        "interval": price['interval_type'],
                        "trial_days": price['trial_period_days'],
                        "features": product.get('metadata', {}).get('features', [])
                    }
                    plans.append(plan)
            
            return {
                "success": True,
                "plans": plans,
                "total_plans": len(plans),
                "message": f"Encontrados {len(plans)} planos disponíveis"
            }
        else:
            return {
                "success": True,
                "plans": [],
                "total_plans": 0,
                "message": "Nenhum plano de assinatura encontrado"
            }
            
    except Exception as e:
        print(f"❌ Error in get_available_subscription_plans: {e}")
        return {
            "success": False,
            "error": str(e),
            "plans": [],
            "message": "Erro ao buscar planos de assinatura"
        }

# Tool definitions for OpenAI integration
PRODUCT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_available_subscription_plans",
            "description": "Busca todos os planos de assinatura disponíveis no sistema com preços e detalhes. Use quando o usuário quiser saber sobre os planos ou preços da Aleen IA.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

"""
Quick Checkout Generator
Gera links de checkout do Stripe rapidamente para bloqueio de assinatura
"""
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def create_quick_checkout_for_user(user_id: str, user_email: str) -> str:
    """
    Cria rapidamente um checkout link para o usuário
    """
    try:
        logger.info(f"🛒 Creating quick checkout for user {user_id}")
        
        # Por enquanto, retornar URL de teste do Stripe
        # TODO: Implementar com MCP Stripe real quando disponível
        
        # Simulação de checkout URL
        base_url = os.getenv('BASE_URL', 'https://aleen.dp.claudy.host')
        test_checkout_url = f"https://buy.stripe.com/test_14k9Dh8gY9ux4gg7ss?prefilled_email={user_email}"
        
        logger.info(f"✅ Quick checkout generated: {test_checkout_url}")
        return test_checkout_url
        
    except Exception as e:
        logger.error(f"❌ Error creating quick checkout: {e}")
        return "https://buy.stripe.com/test_14k9Dh8gY9ux4gg7ss"  # Fallback

def get_subscription_pricing_text() -> str:
    """
    Retorna texto padronizado de preços
    """
    return """✨ **Plano Premium Aleen IA**
💰 R$ 9,99/mês
🎁 14 dias grátis para novos usuários
🏋️‍♀️ Treinos personalizados
🥗 Planos nutricionais
🤖 IA especializada 24/7"""

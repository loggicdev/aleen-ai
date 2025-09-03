# ========================================
# TRIAL TOOLS - Para Interação Conversacional
# ========================================

from typing import Dict, Optional
import os
import json
import subprocess

# Importar depois quando usado para evitar circular import
def get_supabase():
    from supabase import create_client, Client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    return create_client(url, key)

def check_user_trial_status(user_id: str) -> Dict:
    """
    Verifica status do trial do usuário para IA poder decidir ação
    
    Args:
        user_id: ID do usuário
        
    Returns:
        Dict com informações do status:
        - has_subscription: bool
        - subscription_status: str
        - onboarding_complete: bool  
        - has_pending_checkout: bool
        - checkout_url: str (se existe)
        - needs_trial: bool
        - error: str (se erro)
    """
    try:
        supabase = get_supabase()
        
        # Verificar usuário
        user_data = supabase.table('users')\
            .select('email, name, onboarding, stripe_customer_id')\
            .eq('id', user_id)\
            .single()\
            .execute()
        
        if not user_data.data:
            return {
                "error": "Usuário não encontrado",
                "has_subscription": False,
                "needs_trial": False
            }
        
        onboarding_complete = user_data.data.get('onboarding', False)
        
        if not onboarding_complete:
            return {
                "has_subscription": False,
                "onboarding_complete": False,
                "needs_trial": False,
                "error": "Onboarding não completado"
            }
        
        # Verificar subscription ativa
        subscription_data = supabase.table('subscriptions')\
            .select('status, stripe_subscription_id')\
            .eq('user_id', user_id)\
            .eq('status', 'active')\
            .execute()
        
        if subscription_data.data and len(subscription_data.data) > 0:
            return {
                "has_subscription": True,
                "subscription_status": "active",
                "onboarding_complete": True,
                "needs_trial": False
            }
        
        # Verificar checkout pendente
        checkout_data = supabase.table('checkout_sessions')\
            .select('checkout_url, stripe_checkout_session_id, status')\
            .eq('user_id', user_id)\
            .eq('status', 'pending')\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
        
        has_pending_checkout = bool(checkout_data.data and len(checkout_data.data) > 0)
        checkout_url = checkout_data.data[0]['checkout_url'] if has_pending_checkout else None
        
        return {
            "has_subscription": False,
            "subscription_status": "none",
            "onboarding_complete": True,
            "has_pending_checkout": has_pending_checkout,
            "checkout_url": checkout_url,
            "needs_trial": True
        }
        
    except Exception as e:
        return {
            "error": f"Erro ao verificar status: {str(e)}",
            "has_subscription": False,
            "needs_trial": False
        }

def create_trial_checkout(user_id: str) -> Dict:
    """
    Cria checkout session para trial após confirmação do usuário
    
    Args:
        user_id: ID do usuário
        
    Returns:
        Dict com resultado:
        - success: bool
        - checkout_url: str (se sucesso)
        - message: str
        - error: str (se erro)
    """
    try:
        supabase = get_supabase()
        
        # Verificar se usuário existe e onboarding completo
        user_data = supabase.table('users')\
            .select('email, name, onboarding, stripe_customer_id')\
            .eq('id', user_id)\
            .single()\
            .execute()
        
        if not user_data.data:
            return {
                "success": False,
                "error": "Usuário não encontrado"
            }
        
        if not user_data.data.get('onboarding', False):
            return {
                "success": False,
                "error": "Onboarding não foi completado"
            }
        
        customer_id = user_data.data.get('stripe_customer_id')
        if not customer_id:
            return {
                "success": False,
                "error": "Customer do Stripe não encontrado"
            }
        
        # Buscar price_id ativo
        price_data = supabase.table('prices')\
            .select('stripe_price_id')\
            .eq('is_active', True)\
            .limit(1)\
            .execute()
        
        if not price_data.data:
            return {
                "success": False,
                "error": "Nenhum preço ativo encontrado"
            }
        
        price_id = price_data.data[0]['stripe_price_id']
        
        # Criar checkout session no Stripe
        stripe_secret = os.getenv("STRIPE_SECRET_KEY")
        if not stripe_secret:
            return {
                "success": False,
                "error": "Chave do Stripe não configurada"
            }
        
        checkout_result = subprocess.run([
            'curl', '-X', 'POST', 'https://api.stripe.com/v1/checkout/sessions',
            '-H', f'Authorization: Bearer {stripe_secret}',
            '-H', 'Content-Type: application/x-www-form-urlencoded',
            '-d', 'mode=subscription',
            '-d', f'customer={customer_id}',
            '-d', f'line_items[0][price]={price_id}',
            '-d', 'line_items[0][quantity]=1',
            '-d', 'subscription_data[trial_period_days]=14',
            '-d', 'success_url=https://aleen.dp.claudy.host/subscription/success?session_id={CHECKOUT_SESSION_ID}',
            '-d', 'cancel_url=https://aleen.dp.claudy.host/subscription/cancel',
            '-d', f'metadata[user_id]={user_id}'
        ], capture_output=True, text=True)
        
        if checkout_result.returncode != 0:
            return {
                "success": False,
                "error": f"Erro na API do Stripe: {checkout_result.stderr}"
            }
        
        try:
            checkout_data = json.loads(checkout_result.stdout)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Erro ao processar resposta do Stripe: {str(e)}"
            }
        
        if 'error' in checkout_data:
            return {
                "success": False,
                "error": f"Erro do Stripe: {checkout_data['error']['message']}"
            }
        
        if 'url' not in checkout_data:
            return {
                "success": False,
                "error": "URL de checkout não retornada pelo Stripe"
            }
        
        checkout_url = checkout_data['url']
        checkout_session_id = checkout_data['id']
        
        # Salvar no banco
        try:
            supabase.table('checkout_sessions').insert({
                'user_id': user_id,
                'stripe_checkout_session_id': checkout_session_id,
                'checkout_url': checkout_url,
                'status': 'pending',
                'expires_at': None,
                'created_at': 'now()'
            }).execute()
        except Exception as db_error:
            # Log erro mas não falhar - checkout já foi criado
            print(f"⚠️ Erro ao salvar checkout no banco: {db_error}")
        
        return {
            "success": True,
            "checkout_url": checkout_url,
            "message": "Checkout criado com sucesso! 14 dias de trial gratuito."
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro interno: {str(e)}"
        }

# Funções que serão chamadas pela IA
def tool_check_trial_status(user_id: str) -> str:
    """Tool para IA verificar status do trial do usuário"""
    result = check_user_trial_status(user_id)
    
    if result.get("error"):
        return f"❌ Erro: {result['error']}"
    
    if result.get("has_subscription"):
        return "✅ Usuário já possui assinatura ativa"
    
    if not result.get("onboarding_complete"):
        return "⚠️ Usuário precisa completar onboarding primeiro"
    
    if result.get("has_pending_checkout"):
        return f"⏳ Usuário já tem checkout pendente: {result.get('checkout_url')}"
    
    if result.get("needs_trial"):
        return "🎁 Usuário elegível para trial de 14 dias gratuito"
    
    return "ℹ️ Status indefinido"

def tool_create_trial_checkout(user_id: str) -> str:
    """Tool para IA criar checkout após confirmação do usuário"""
    result = create_trial_checkout(user_id)
    
    if result.get("success"):
        checkout_url = result.get("checkout_url")
        return f"""✅ Checkout criado com sucesso!

🔗 **Link para começar seu trial gratuito:**
{checkout_url}

🎁 **Você terá 14 dias completamente grátis para testar todos os recursos da Aleen IA!**

✅ **Benefícios inclusos:**
- Planos de nutrição personalizados
- Treinos específicos para seu objetivo  
- Suporte 24/7 da Aleen
- Acesso a todos os recursos premium

💳 *Após inserir os dados do cartão, você terá 14 dias para testar tudo gratuitamente antes de qualquer cobrança!*"""
    else:
        error = result.get("error", "Erro desconhecido")
        return f"❌ Não foi possível criar o checkout: {error}"

# Ferramentas da IA no formato correto
def get_trial_tools():
    """
    Retorna as ferramentas de trial para a IA usar
    """
    return [
        {
            "name": "check_user_trial_status",
            "description": "Verifica o status do trial/assinatura do usuário atual",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "create_trial_checkout", 
            "description": "Cria link de pagamento para iniciar trial de 14 dias APENAS após o usuário confirmar que deseja",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_confirmed": {
                        "type": "boolean",
                        "description": "Se o usuário confirmou que deseja iniciar o trial"
                    }
                },
                "required": ["user_confirmed"]
            }
        }
    ]

# Lista de tools disponíveis
TRIAL_TOOLS = get_trial_tools()

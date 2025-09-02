"""
Subscription Integration
Integração modular do sistema de assinaturas ao main.py
"""
import os
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request

# Import services
try:
    from src.services.stripe_service import StripeService
    from src.services.subscription_service import SubscriptionService  
    from src.services.payment_middleware import PaymentMiddleware
    from src.services.payment_config_service import PaymentConfigService
    from src.webhooks.stripe_webhook import StripeWebhookHandler
    from src.tools.subscription_tools import (
        set_subscription_services,
        create_user_subscription_tool,
        check_user_subscription_access_tool,
        SUBSCRIPTION_TOOLS
    )
    from src.tools.product_tools import (
        set_product_services,
        get_available_subscription_plans,
        PRODUCT_TOOLS
    )
    from src.models.subscription_models import (
        SubscriptionCreate,
        SubscriptionResponse,
        PaymentAccessCheck,
        PaymentAccessResponse
    )
    SUBSCRIPTION_AVAILABLE = True
    print("✅ Subscription system loaded successfully")
except ImportError as e:
    print(f"⚠️ Subscription system not available: {e}")
    SUBSCRIPTION_AVAILABLE = False

class SubscriptionIntegration:
    """
    Central integration class for subscription system
    """
    def __init__(self):
        """Initialize all subscription services"""
        if not SUBSCRIPTION_AVAILABLE:
            print("⚠️ Subscription integration disabled - modules not available")
            self.stripe_service = None
            self.subscription_service = None
            self.payment_middleware = None
            self.webhook_handler = None
            return
        
        try:
            # Get supabase service reference
            try:
                from main import supabase
                supabase_ref = supabase
            except ImportError:
                try:
                    from src.services.supabase_service import supabase_service
                    supabase_ref = supabase_service
                except ImportError:
                    supabase_ref = None
                    print("⚠️ Supabase service not available")
            
            # Initialize services
            self.stripe_service = StripeService()
            self.payment_config_service = PaymentConfigService(supabase_ref)
            self.subscription_service = SubscriptionService(self.stripe_service)
            self.payment_middleware = PaymentMiddleware(self.subscription_service)
            self.webhook_handler = StripeWebhookHandler(self.subscription_service)
            
            # Set services for tools
            set_subscription_services(self.subscription_service, self.payment_middleware)
            
            # Set product services (assuming supabase_service is available globally)
            try:
                from main import supabase
                set_product_services(supabase)
            except ImportError:
                print("⚠️ Supabase not available for product tools")
            
            print("✅ SubscriptionIntegration initialized successfully")
            
        except Exception as e:
            print(f"❌ Error initializing subscription integration: {e}")
            self.stripe_service = None
            self.subscription_service = None
            self.payment_middleware = None
            self.webhook_handler = None
    
    def is_available(self) -> bool:
        """Check if subscription system is available"""
        return SUBSCRIPTION_AVAILABLE and self.subscription_service is not None
    
    async def create_subscription_after_onboarding(
        self,
        user_id: str,
        email: str,
        name: str,
        phone: str = None
    ) -> Dict[str, Any]:
        """
        Create subscription after user completes onboarding
        This is called from the existing create_user_and_save_onboarding function
        """
        if not self.is_available():
            print("⚠️ Subscription system not available - skipping subscription creation")
            return {
                "success": True,
                "message": "User created successfully (subscription system disabled)"
            }
        
        try:
            result = await create_user_subscription_tool(user_id, email, name, phone)
            return result
        except Exception as e:
            print(f"❌ Error creating subscription after onboarding: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Erro ao criar assinatura, mas usuário foi criado com sucesso"
            }
    
    async def check_access_before_tools(self, user_id: str) -> Dict[str, Any]:
        """
        Check if user has access before executing premium tools
        Returns access info and denial message if applicable
        """
        if not self.is_available():
            # If subscription system is not available, allow all access
            return {"has_access": True, "denial_message": None}
        
        try:
            access_result = await check_user_subscription_access_tool(user_id)
            
            if not access_result.get("has_access", False):
                return {
                    "has_access": False,
                    "denial_message": access_result.get("message", "Acesso negado")
                }
            
            return {"has_access": True, "denial_message": None}
            
        except Exception as e:
            print(f"❌ Error checking access: {e}")
            # Default to allowing access to not break existing functionality
            return {"has_access": True, "denial_message": None}
    
    def get_subscription_tools(self) -> list:
        """Get subscription tools for OpenAI integration"""
        if self.is_available():
            return SUBSCRIPTION_TOOLS + PRODUCT_TOOLS
        return []
    
    def setup_routes(self, app: FastAPI):
        """Setup subscription-related routes"""
        if not self.is_available():
            print("⚠️ Subscription routes not available")
            return
        
        @app.post("/subscription/create")
        async def create_subscription_endpoint(request: SubscriptionCreate):
            """Create a new subscription"""
            try:
                result = await self.subscription_service.create_user_subscription(
                    user_id=request.user_id,
                    email=request.email,
                    name=request.name,
                    phone=request.phone
                )
                return SubscriptionResponse(**result)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.post("/subscription/check-access")
        async def check_access_endpoint(request: PaymentAccessCheck):
            """Check user subscription access"""
            try:
                result = await self.payment_middleware.require_subscription(request.user_id)
                
                response_data = {
                    "has_access": not result.get("access_denied", False),
                    "reason": result.get("subscription_info", {}).get("reason", ""),
                    "subscription_info": result.get("subscription_info", {}),
                }
                
                if result.get("access_denied"):
                    response_data["message"] = result.get("message", "")
                
                return PaymentAccessResponse(**response_data)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.post("/webhooks/stripe")
        async def stripe_webhook_endpoint(request: Request):
            """Handle Stripe webhooks"""
            try:
                result = await self.webhook_handler.handle_webhook(request)
                return result
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        print("✅ Subscription routes registered")

# Global instance for easy import
subscription_integration = None

def initialize_subscription_system() -> SubscriptionIntegration:
    """Initialize the global subscription system"""
    global subscription_integration
    if subscription_integration is None:
        subscription_integration = SubscriptionIntegration()
    return subscription_integration

def get_subscription_integration() -> Optional[SubscriptionIntegration]:
    """Get the global subscription integration instance"""
    return subscription_integration

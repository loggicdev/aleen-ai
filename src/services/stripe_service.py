"""
Stripe Service
Centraliza toda comunicação com Stripe API
"""
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class StripeService:
    def __init__(self):
        """Initialize Stripe with secret key"""
        self.stripe_key = os.getenv('STRIPE_SECRET_KEY')
        if not self.stripe_key:
            raise ValueError("STRIPE_SECRET_KEY environment variable is required")
        
        # MCP Stripe will be used for API calls
        print("✅ StripeService initialized")
    
    async def create_customer(self, email: str, name: str, phone: str = None) -> Dict[str, Any]:
        """Create a new Stripe customer using MCP"""
        try:
            # Import MCP functions globally available
            from main import mcp_stripe_create_customer
            
            print(f"🔄 Creating Stripe customer for {email}")
            
            result = mcp_stripe_create_customer(email=email, name=name)
            
            if result and result.get('id'):
                customer_id = result['id']
                print(f"✅ Stripe customer created: {customer_id}")
                return {
                    "success": True,
                    "customer_id": customer_id,
                    "customer": result
                }
            else:
                print(f"❌ Failed to create Stripe customer: {result}")
                return {"success": False, "error": "Failed to create customer"}
                
        except Exception as e:
            print(f"❌ Error creating Stripe customer: {e}")
            return {"success": False, "error": str(e)}
    
    async def create_subscription(
        self, 
        customer_id: str, 
        price_id: str, 
        trial_days: int = 14
    ) -> Dict[str, Any]:
        """Create a subscription with trial period"""
        try:
            # Calculate trial end date
            trial_end = datetime.now() + timedelta(days=trial_days)
            
            # Using MCP Stripe - we'll need to use the direct call
            # since MCP might not have create_subscription with trial
            subscription_data = {
                "customer": customer_id,
                "items": [{"price": price_id}],
                "trial_period_days": trial_days,
                "payment_behavior": "default_incomplete",
                "expand": ["latest_invoice.payment_intent"]
            }
            
            # For now, return mock data - will implement MCP call
            print(f"🔄 Creating subscription for customer {customer_id} with {trial_days} days trial")
            
            # TODO: Implement actual MCP Stripe call when available
            mock_subscription = {
                "id": f"sub_mock_{customer_id[:8]}",
                "customer": customer_id,
                "status": "trialing",
                "trial_start": datetime.now().timestamp(),
                "trial_end": trial_end.timestamp(),
                "current_period_start": datetime.now().timestamp(),
                "current_period_end": trial_end.timestamp()
            }
            
            return {
                "success": True,
                "subscription": mock_subscription,
                "subscription_id": mock_subscription["id"]
            }
            
        except Exception as e:
            print(f"❌ Error creating subscription: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_subscription_status(self, subscription_id: str) -> Dict[str, Any]:
        """Get current subscription status"""
        try:
            # Using MCP Stripe list_subscriptions (filter by ID)
            # For now, return mock data
            print(f"🔍 Checking status for subscription {subscription_id}")
            
            # TODO: Implement actual MCP Stripe call
            mock_status = {
                "id": subscription_id,
                "status": "trialing",  # trialing, active, past_due, canceled, unpaid
                "trial_end": (datetime.now() + timedelta(days=10)).timestamp(),
                "current_period_end": (datetime.now() + timedelta(days=30)).timestamp()
            }
            
            return {
                "success": True,
                "subscription": mock_status,
                "is_active": mock_status["status"] in ["trialing", "active"]
            }
            
        except Exception as e:
            print(f"❌ Error getting subscription status: {e}")
            return {"success": False, "error": str(e)}
    
    async def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> Dict[str, Any]:
        """Cancel a subscription"""
        try:
            # Using MCP Stripe cancel_subscription
            print(f"🚫 Canceling subscription {subscription_id} (at_period_end: {at_period_end})")
            
            # TODO: Implement actual MCP Stripe call
            return {
                "success": True,
                "message": f"Subscription {subscription_id} will be canceled at period end" if at_period_end 
                          else f"Subscription {subscription_id} canceled immediately"
            }
            
        except Exception as e:
            print(f"❌ Error canceling subscription: {e}")
            return {"success": False, "error": str(e)}

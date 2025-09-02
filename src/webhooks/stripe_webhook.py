"""
Stripe Webhook Handler
Processa eventos do Stripe (pagamentos, cancelamentos, etc)
"""
import os
import json
import hmac
import hashlib
from typing import Dict, Any
from fastapi import HTTPException, Request

class StripeWebhookHandler:
    def __init__(self, subscription_service=None):
        """Initialize webhook handler"""
        self.subscription_service = subscription_service
        self.webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        print("✅ StripeWebhookHandler initialized")
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify that the webhook came from Stripe
        """
        if not self.webhook_secret:
            print("⚠️ STRIPE_WEBHOOK_SECRET not set - skipping signature verification")
            return True  # In development, skip verification
        
        try:
            # Extract timestamp and signature from header
            elements = signature.split(',')
            timestamp = None
            signature_hash = None
            
            for element in elements:
                if element.startswith('t='):
                    timestamp = element.split('=')[1]
                elif element.startswith('v1='):
                    signature_hash = element.split('=')[1]
            
            if not timestamp or not signature_hash:
                return False
            
            # Create expected signature
            signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                signed_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            return hmac.compare_digest(expected_signature, signature_hash)
            
        except Exception as e:
            print(f"❌ Error verifying webhook signature: {e}")
            return False
    
    async def handle_webhook(self, request: Request) -> Dict[str, Any]:
        """
        Main webhook handler - processes all Stripe events
        """
        try:
            # Get raw payload and signature
            payload = await request.body()
            signature = request.headers.get('stripe-signature', '')
            
            # Verify signature
            if not self.verify_webhook_signature(payload, signature):
                raise HTTPException(status_code=400, detail="Invalid signature")
            
            # Parse webhook data
            try:
                event = json.loads(payload.decode('utf-8'))
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            
            event_type = event.get('type')
            event_data = event.get('data', {}).get('object', {})
            
            print(f"🔔 Stripe webhook received: {event_type}")
            
            # Route to appropriate handler
            result = await self._route_event(event_type, event_data)
            
            return {
                "success": True,
                "event_type": event_type,
                "processed": result
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"❌ Error processing webhook: {e}")
            raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")
    
    async def _route_event(self, event_type: str, event_data: Dict) -> Dict[str, Any]:
        """
        Route Stripe events to appropriate handlers
        """
        subscription_events = {
            'customer.subscription.created': self._handle_subscription_created,
            'customer.subscription.updated': self._handle_subscription_updated,
            'customer.subscription.deleted': self._handle_subscription_deleted,
            'invoice.payment_succeeded': self._handle_payment_succeeded,
            'invoice.payment_failed': self._handle_payment_failed,
            'customer.subscription.trial_will_end': self._handle_trial_ending,
        }
        
        handler = subscription_events.get(event_type)
        if handler:
            return await handler(event_data)
        else:
            print(f"🔄 Unhandled event type: {event_type}")
            return {"status": "unhandled", "event_type": event_type}
    
    async def _handle_subscription_created(self, subscription: Dict) -> Dict[str, Any]:
        """Handle new subscription creation"""
        try:
            subscription_id = subscription['id']
            status = subscription['status']
            
            print(f"✅ Subscription created: {subscription_id} with status: {status}")
            
            if self.subscription_service:
                await self.subscription_service.update_subscription_status(
                    subscription_id, 
                    status, 
                    subscription
                )
            
            return {"status": "processed", "action": "created"}
            
        except Exception as e:
            print(f"❌ Error handling subscription creation: {e}")
            return {"status": "error", "error": str(e)}
    
    async def _handle_subscription_updated(self, subscription: Dict) -> Dict[str, Any]:
        """Handle subscription updates (status changes, renewals, etc)"""
        try:
            subscription_id = subscription['id']
            status = subscription['status']
            
            print(f"🔄 Subscription updated: {subscription_id} to status: {status}")
            
            if self.subscription_service:
                await self.subscription_service.update_subscription_status(
                    subscription_id, 
                    status, 
                    subscription
                )
            
            return {"status": "processed", "action": "updated"}
            
        except Exception as e:
            print(f"❌ Error handling subscription update: {e}")
            return {"status": "error", "error": str(e)}
    
    async def _handle_subscription_deleted(self, subscription: Dict) -> Dict[str, Any]:
        """Handle subscription cancellation"""
        try:
            subscription_id = subscription['id']
            
            print(f"🚫 Subscription canceled: {subscription_id}")
            
            if self.subscription_service:
                await self.subscription_service.update_subscription_status(
                    subscription_id, 
                    "canceled", 
                    subscription
                )
            
            return {"status": "processed", "action": "canceled"}
            
        except Exception as e:
            print(f"❌ Error handling subscription cancellation: {e}")
            return {"status": "error", "error": str(e)}
    
    async def _handle_payment_succeeded(self, invoice: Dict) -> Dict[str, Any]:
        """Handle successful payment"""
        try:
            subscription_id = invoice.get('subscription')
            
            if subscription_id:
                print(f"💳 Payment succeeded for subscription: {subscription_id}")
                
                if self.subscription_service:
                    await self.subscription_service.update_subscription_status(
                        subscription_id, 
                        "active"
                    )
            
            return {"status": "processed", "action": "payment_succeeded"}
            
        except Exception as e:
            print(f"❌ Error handling payment success: {e}")
            return {"status": "error", "error": str(e)}
    
    async def _handle_payment_failed(self, invoice: Dict) -> Dict[str, Any]:
        """Handle failed payment"""
        try:
            subscription_id = invoice.get('subscription')
            
            if subscription_id:
                print(f"💸 Payment failed for subscription: {subscription_id}")
                
                if self.subscription_service:
                    await self.subscription_service.update_subscription_status(
                        subscription_id, 
                        "past_due"
                    )
            
            return {"status": "processed", "action": "payment_failed"}
            
        except Exception as e:
            print(f"❌ Error handling payment failure: {e}")
            return {"status": "error", "error": str(e)}
    
    async def _handle_trial_ending(self, subscription: Dict) -> Dict[str, Any]:
        """Handle trial period ending soon"""
        try:
            subscription_id = subscription['id']
            customer_id = subscription['customer']
            
            print(f"⏰ Trial ending soon for subscription: {subscription_id}")
            
            # Here you could send a notification to the user
            # about their trial ending soon
            
            return {"status": "processed", "action": "trial_ending_notification"}
            
        except Exception as e:
            print(f"❌ Error handling trial ending: {e}")
            return {"status": "error", "error": str(e)}

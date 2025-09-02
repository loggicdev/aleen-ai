"""
Subscription Models
Modelos de dados para sistema de assinaturas
"""
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class SubscriptionCreate(BaseModel):
    """Model for creating a new subscription"""
    user_id: str
    email: str
    name: str
    phone: Optional[str] = None
    trial_days: Optional[int] = 14

class SubscriptionResponse(BaseModel):
    """Model for subscription response"""
    success: bool
    subscription_id: Optional[str] = None
    customer_id: Optional[str] = None
    trial_end: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None

class SubscriptionStatus(BaseModel):
    """Model for subscription status check"""
    has_access: bool
    status: Literal[
        "trialing", 
        "active", 
        "past_due", 
        "canceled", 
        "unpaid", 
        "no_subscription", 
        "trial_expired",
        "error"
    ]
    reason: Optional[str] = None
    trial_end: Optional[str] = None
    current_period_end: Optional[str] = None

class PaymentAccessCheck(BaseModel):
    """Model for payment access verification"""
    user_id: str

class PaymentAccessResponse(BaseModel):
    """Model for payment access response"""
    has_access: bool
    reason: str
    subscription_info: dict
    message: Optional[str] = None

class WebhookEvent(BaseModel):
    """Model for Stripe webhook events"""
    type: str
    data: dict
    created: Optional[int] = None
    livemode: Optional[bool] = None

class SubscriptionWebhookUpdate(BaseModel):
    """Model for subscription updates via webhook"""
    stripe_subscription_id: str
    status: str
    webhook_data: Optional[dict] = None

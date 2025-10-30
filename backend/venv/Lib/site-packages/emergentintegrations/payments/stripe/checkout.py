"""
Stripe checkout integration for payment processing.
"""
import stripe
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, validator
import json


class CheckoutSessionRequest(BaseModel):
    """Request model for creating a checkout session."""
    amount: Optional[float] = Field(None, description="The amount to charge in the specified currency")
    currency: str = Field("usd", description="The currency code")
    stripe_price_id: Optional[str] = Field(None, description="The Stripe Price ID to use for the payment")
    quantity: int = Field(1, description="The quantity of items to purchase")
    success_url: Optional[str] = Field(None, description="URL to redirect to after successful payment, should contain the variable session_id={CHECKOUT_SESSION_ID} to fill in the session id")
    cancel_url: Optional[str] = Field(None, description="URL to redirect to if payment is cancelled")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata to store with the session")

    @validator('amount')
    def validate_amount(cls, v, values):
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v

    @validator('quantity')
    def validate_quantity(cls, v):
        if v < 1:
            raise ValueError("Quantity must be greater than 0")
        return v

    @validator('stripe_price_id')
    def validate_payment_method(cls, v, values):
        if v is None and values.get('amount') is None:
            raise ValueError("Either amount or stripe_price_id must be provided")
        if v is not None and values.get('amount') is not None:
            raise ValueError("Cannot provide both amount and stripe_price_id")
        return v


class CheckoutSessionResponse(BaseModel):
    """Response model for checkout session creation."""
    url: str = Field(..., description="The stripe checkout session URL to redirect the customer to")
    session_id: str = Field(..., description="The ID of the created session")


class CheckoutStatusResponse(BaseModel):
    """Response model for checkout session status."""
    status: str = Field(..., description="The status of the checkout session")
    payment_status: str = Field(..., description="The payment status")
    amount_total: int = Field(..., description="The total amount in cents")
    currency: str = Field(..., description="The currency code")
    metadata: Dict[str, str] = Field(..., description="The metadata of the checkout session")


class WebhookEventResponse(BaseModel):
    """Response model for webhook event processing."""
    event_type: str = Field(..., description="The type of webhook event")
    event_id: str = Field(..., description="The ID of the webhook event")
    session_id: Optional[str] = Field(None, description="The checkout session ID if applicable")
    payment_status: Optional[str] = Field(None, description="The payment status if applicable")
    metadata: Dict[str, str] = Field(..., description="The metadata of the event")


class StripeCheckout:
    """
    Stripe checkout integration for creating payment sessions and processing payments.
    """

    def __init__(
        self, 
        api_key: str, 
        webhook_secret: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        """
        Initialize the Stripe checkout integration.

        Args:
            api_key (str): The Stripe API key.
            webhook_secret (str, optional): The webhook signing secret for validating webhook events.
        """
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        stripe.api_key = self.api_key
        self.webhook_url = webhook_url
        # if api key contains sk_test_emergent, set api_base_url to emergent integration proxy
        if "sk_test_emergent" in self.api_key:
            stripe.api_base = "https://integrations.emergentagent.com/stripe"

    async def create_checkout_session(
        self, 
        request: CheckoutSessionRequest
    ) -> CheckoutSessionResponse:
        """
        Creates a Stripe checkout session for a payment.

        Args:
            request (CheckoutSessionRequest): The request model containing payment details.

        Returns:
            CheckoutSessionResponse: A response model containing the checkout session URL and ID.

        Raises:
            CheckoutError: If there's an error creating the checkout session.
        """
        try:
            # Prepare line items based on payment method
            if request.amount is not None:
                # Convert amount to cents/smallest currency unit
                amount_in_cents = int(request.amount * 100)
                line_items = [{
                    'price_data': {
                        'currency': request.currency,
                        'product_data': {
                            'name': 'Payment',
                        },
                        'unit_amount': amount_in_cents,
                    },
                    'quantity': 1,
                }]
            else:
                line_items = [{
                    'price': request.stripe_price_id,
                    'quantity': request.quantity,
                }]
            
            # merge webhook url with metadata
            if self.webhook_url:
                request.metadata = {
                    **(request.metadata or {}),
                    'webhook_url': self.webhook_url
                }

            # Create the checkout session
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url=request.success_url,
                cancel_url=request.cancel_url,
                metadata=request.metadata or {}
            )
            
            return CheckoutSessionResponse(
                url=session.url,
                session_id=session.id
            )
            
        except stripe.error.StripeError as e:
            raise CheckoutError(f"Failed to create checkout session: {str(e)}")
        except Exception as e:
            raise CheckoutError(f"Unexpected error creating checkout session: {str(e)}")

    async def get_checkout_status(self, checkout_session_id: str) -> CheckoutStatusResponse:
        """
        Retrieves the status of a Stripe checkout session.

        Args:
            checkout_session_id (str): The ID of the checkout session to check.

        Returns:
            CheckoutStatusResponse: A response model containing the session status information.

        Raises:
            CheckoutError: If there's an error retrieving the session status.
        """
        try:
            session = stripe.checkout.Session.retrieve(checkout_session_id)
            
            return CheckoutStatusResponse(
                status=session.status,
                payment_status=session.payment_status,
                amount_total=session.amount_total,
                currency=session.currency,
                metadata=session.metadata
            )
            
        except stripe.error.StripeError as e:
            raise CheckoutError(f"Failed to retrieve session status: {str(e)}")
        except Exception as e:
            raise CheckoutError(f"Unexpected error retrieving session status: {str(e)}")

    async def handle_webhook(
        self, 
        payload: bytes,
        signature: Optional[str] = None
    ) -> WebhookEventResponse:
        """
        Handles a Stripe webhook event by processing the event payload.

        Args:
            payload (bytes): The raw webhook payload from Stripe.

        Returns:
            WebhookEventResponse: A response model containing the processed webhook event information.

        Raises:
            CheckoutError: If there's an error processing the webhook.
        """
        try:
            if self.webhook_secret:
                event = stripe.Webhook.construct_event(
                    payload, signature, self.webhook_secret
                )
            else:
                event = json.loads(payload.decode('utf-8'))
                
            # Extract relevant information based on event type
            event_type = event['type']
            event_id = event['id']
            metadata = event.get('data', {}).get('object', {}).get('metadata', {})
            
            session_id = None
            payment_status = None

            # Handle different event types
            if event_type == 'checkout.session.completed':
                session_data = event['data']['object']
                session_id = session_data.get('id')
                payment_status = session_data.get('payment_status')
                
            elif event_type == 'checkout.session.expired':
                session_data = event['data']['object']
                session_id = session_data.get('id')
                payment_status = session_data.get('payment_status')
                
            elif event_type == 'payment_intent.succeeded':
                payment_data = event['data']['object']
                session_id = payment_data.get('metadata', {}).get('checkout_session_id')
                payment_status = 'paid'
                
            elif event_type == 'payment_intent.payment_failed':
                payment_data = event['data']['object']
                session_id = payment_data.get('metadata', {}).get('checkout_session_id')
                payment_status = 'failed'

            return WebhookEventResponse(
                event_type=event_type,
                event_id=event_id,
                session_id=session_id,
                payment_status=payment_status,
                metadata=metadata
            )

        except json.JSONDecodeError as e:
            raise CheckoutError(f"Invalid JSON payload: {str(e)}")
        except Exception as e:
            raise CheckoutError(f"Unexpected error processing webhook: {str(e)}")


class CheckoutError(Exception):
    """Exception raised for errors in the Stripe checkout process."""
    pass
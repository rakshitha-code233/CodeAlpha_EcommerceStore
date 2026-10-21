from django import forms

from .models import Order


class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Full name")
    email = forms.EmailField()
    phone = forms.CharField(max_length=30)
    address = forms.CharField(max_length=255, label="Street address")
    city = forms.CharField(max_length=100)
    postal_code = forms.CharField(max_length=20)
    payment_method = forms.ChoiceField(
        label="Payment method",
        choices=Order.PAYMENT_METHOD_CHOICES,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, payment_configured=True, **kwargs):
        super().__init__(*args, **kwargs)
        if payment_configured:
            self.fields["payment_method"].initial = Order.PAYMENT_METHOD_RAZORPAY
        else:
            self.fields["payment_method"].choices = [
                (
                    Order.PAYMENT_METHOD_CASH_ON_DELIVERY,
                    "Cash on delivery",
                ),
            ]
            self.fields["payment_method"].initial = (
                Order.PAYMENT_METHOD_CASH_ON_DELIVERY
            )

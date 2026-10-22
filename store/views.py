import logging
import uuid
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from requests.exceptions import RequestException
from razorpay import Client as RazorpayClient
from razorpay.errors import (
    BadRequestError,
    GatewayError,
    ServerError,
    SignatureVerificationError,
)

from .forms import CheckoutForm
from .models import Order, OrderItem, Product

logger = logging.getLogger(__name__)


def get_razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        return None
    return RazorpayClient(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def _get_cart(request):
    saved_cart = request.session.get("cart", {})
    if not isinstance(saved_cart, dict):
        saved_cart = {}

    cart = {}
    for product_id, saved_quantity in saved_cart.items():
        if not str(product_id).isdigit():
            continue
        try:
            quantity = int(saved_quantity)
        except (TypeError, ValueError):
            continue
        if quantity > 0:
            cart[str(int(product_id))] = quantity

    request.session["cart"] = cart
    return cart


def product_list(request):
    products = Product.objects.filter(is_active=True).select_related("category")
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")

    if query:
        products = products.filter(name__icontains=query) | products.filter(
            description__icontains=query
        )
    if sort == "price_asc":
        products = products.order_by("price", "name")
    elif sort == "price_desc":
        products = products.order_by("-price", "name")
    else:
        sort = "name"
        products = products.order_by("name")

    return render(
        request,
        "store/product_list.html",
        {
            "products": products,
            "query": query,
            "selected_sort": sort,
        },
    )


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    return render(
        request,
        "store/product_detail.html",
        {
            "product": product,
            "related_products": Product.objects.filter(
                is_active=True, category=product.category
            ).exclude(id=product.id)[:4]
            if product.category_id
            else Product.objects.none(),
        },
    )


def _add_product_to_cart(request, product):
    cart = _get_cart(request)
    key = str(product.id)
    quantity = cart.get(key, 0)
    if quantity >= product.stock:
        messages.error(request, f"Only {product.stock} of {product.name} are in stock.")
        return False

    cart[key] = quantity + 1
    request.session["cart"] = cart
    return True


def _sign_in_to_shop(request, next_url):
    messages.info(request, "Please sign in before adding items or placing an order.")
    return redirect(f"{reverse('login')}?{urlencode({'next': next_url})}")


@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    if not request.user.is_authenticated:
        return _sign_in_to_shop(
            request,
            reverse("product_detail", args=[product.id]),
        )
    if not _add_product_to_cart(request, product):
        return redirect("product_detail", product_id=product.id)
    messages.success(request, f"{product.name} added to your cart.")
    return redirect("cart_detail")


@require_POST
def buy_now(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    if not request.user.is_authenticated:
        return _sign_in_to_shop(
            request,
            reverse("product_detail", args=[product.id]),
        )
    if not _add_product_to_cart(request, product):
        return redirect("product_detail", product_id=product.id)
    return redirect("checkout")


@require_POST
def remove_from_cart(request, product_id):
    if not request.user.is_authenticated:
        return _sign_in_to_shop(request, reverse("cart_detail"))
    cart = _get_cart(request)
    cart.pop(str(product_id), None)
    request.session["cart"] = cart
    messages.success(request, "Item removed from your cart.")
    return redirect("cart_detail")


@require_POST
def update_cart(request, product_id):
    if not request.user.is_authenticated:
        return _sign_in_to_shop(request, reverse("cart_detail"))
    cart = _get_cart(request)
    key = str(product_id)
    if key not in cart:
        messages.error(request, "That product is not in your cart.")
        return redirect("cart_detail")
    product = get_object_or_404(Product, id=product_id, is_active=True)
    try:
        quantity = int(request.POST.get("quantity", ""))
    except ValueError:
        messages.error(request, "Enter a valid quantity.")
        return redirect("cart_detail")

    if quantity < 1:
        messages.error(request, "Quantity must be at least 1.")
    elif quantity > product.stock:
        messages.error(request, f"Only {product.stock} of {product.name} are in stock.")
    else:
        cart[key] = quantity
        request.session["cart"] = cart
        messages.success(request, "Cart updated.")
    return redirect("cart_detail")


def cart_detail(request):
    cart = _get_cart(request)
    items = []
    total = Decimal("0.00")

    products = Product.objects.filter(
        id__in=[int(product_id) for product_id in cart if str(product_id).isdigit()],
        is_active=True,
    )
    available_ids = {str(product.id) for product in products}
    for product_id in list(cart):
        if product_id not in available_ids:
            cart.pop(product_id, None)
    request.session["cart"] = cart

    for product in products:
        quantity = cart[str(product.id)]
        subtotal = product.price * quantity
        total += subtotal
        items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    return render(
        request,
        "store/cart.html",
        {
            "items": items,
            "total": total,
            "has_items": bool(items),
            "can_checkout": bool(items)
            and all(item["quantity"] <= item["product"].stock for item in items),
        },
    )


def register(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        if not username or not email or not password1:
            messages.error(request, "Username, email, and password are required.")
            return redirect("register")
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Enter a valid email address.")
            return redirect("register")
        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return redirect("register")
        if len(password1) < 8:
            messages.error(request, "Use a password with at least 8 characters.")
            return redirect("register")
        if len(username) > 150:
            messages.error(request, "Username is too long.")
            return redirect("register")
        from django.contrib.auth.models import User
        if User.objects.filter(username=username).exists():
            messages.error(request, "That username is already taken.")
            return redirect("register")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
        )
        auth_login(request, user)
        messages.success(request, "Your account was created successfully.")
        return redirect("product_list")

    return render(request, "store/register.html")


def user_login(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            next_url = request.POST.get("next") or request.GET.get("next", "")
            if url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect("product_list")

        messages.error(request, "Invalid username or password.")
        return redirect("login")

    return render(request, "store/login.html")


@require_POST
def user_logout(request):
    auth_logout(request)
    messages.success(request, "You have logged out.")
    return redirect("product_list")


@login_required
def checkout(request):
    cart = _get_cart(request)
    if not cart:
        messages.error(request, "Your cart is empty.")
        return redirect("cart_detail")

    payment_configured = bool(
        settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET
    )
    form = CheckoutForm(
        data=request.POST if request.method == "POST" else None,
        initial={
            "full_name": request.user.get_full_name(),
            "email": request.user.email,
        },
        payment_configured=payment_configured,
    )
    products_to_order = []
    total = Decimal("0.00")
    products = Product.objects.filter(
        id__in=[int(product_id) for product_id in cart if str(product_id).isdigit()],
        is_active=True,
    )
    if len(products) != len(cart):
        messages.error(request, "Some products in your cart are no longer available.")
        return redirect("cart_detail")
    for product in products:
        quantity = int(cart.get(str(product.id), 0))
        if quantity < 1 or quantity > product.stock:
            messages.error(
                request,
                f"Please review the quantity for {product.name}; only {product.stock} are available.",
            )
            return redirect("cart_detail")
        total += product.price * quantity
        products_to_order.append((product, quantity))

    if not products_to_order:
        messages.error(request, "Your cart is empty.")
        return redirect("cart_detail")

    if request.method == "POST" and form.is_valid():
        if total <= 0:
            form.add_error(None, "The order total must be greater than zero.")
        else:
            payment_method = form.cleaned_data["payment_method"]
            gateway_order = {}
            can_create_order = True
            if payment_method == Order.PAYMENT_METHOD_RAZORPAY:
                client = get_razorpay_client()
                if client is None:
                    form.add_error(
                        "payment_method",
                        "Razorpay is not configured. Select cash on delivery instead.",
                    )
                    can_create_order = False
                else:
                    try:
                        gateway_order = client.order.create(
                            data={
                                "amount": int(total * 100),
                                "currency": "INR",
                                "receipt": uuid.uuid4().hex,
                            }
                        )
                    except (
                        BadRequestError,
                        GatewayError,
                        ServerError,
                        RequestException,
                    ):
                        logger.exception("Razorpay could not create a payment order.")
                        form.add_error(
                            "payment_method",
                            "The payment service could not start checkout. Please try again.",
                        )
                        can_create_order = False

            if can_create_order:
                with transaction.atomic():
                    locked_products = {
                        product.id: product
                        for product in Product.objects.select_for_update().filter(
                            id__in=[product.id for product, _ in products_to_order],
                            is_active=True,
                        )
                    }
                    current_total = Decimal("0.00")
                    for product, quantity in products_to_order:
                        if (
                            product.id not in locked_products
                            or locked_products[product.id].stock < quantity
                        ):
                            messages.error(
                                request,
                                f"{product.name} no longer has enough stock. Please update your cart.",
                            )
                            return redirect("cart_detail")
                        current_total += locked_products[product.id].price * quantity
                    if current_total != total:
                        messages.error(
                            request,
                            "Product prices changed while you were checking out. Please review your cart and try again.",
                        )
                        return redirect("cart_detail")

                    is_cash_on_delivery = (
                        payment_method
                        == Order.PAYMENT_METHOD_CASH_ON_DELIVERY
                    )
                    held_order = Order.objects.create(
                        user=request.user,
                        total=current_total,
                        status="Placed" if is_cash_on_delivery else "Awaiting payment",
                        payment_status=Order.PAYMENT_PENDING,
                        payment_method=payment_method,
                        payment_gateway_order_id=gateway_order.get("id", ""),
                        shipping_name=form.cleaned_data["full_name"],
                        shipping_email=form.cleaned_data["email"],
                        shipping_phone=form.cleaned_data["phone"],
                        shipping_address=form.cleaned_data["address"],
                        shipping_city=form.cleaned_data["city"],
                        shipping_postal_code=form.cleaned_data["postal_code"],
                    )
                    for product, quantity in products_to_order:
                        locked_product = locked_products[product.id]
                        locked_product.stock -= quantity
                        locked_product.save(update_fields=["stock"])
                        OrderItem.objects.create(
                            order=held_order,
                            product=locked_product,
                            quantity=quantity,
                            price_at_purchase=locked_product.price,
                        )

                request.session["cart"] = {}
                if is_cash_on_delivery:
                    messages.success(
                        request,
                        f"Order #{held_order.id} placed. Pay when your order is delivered.",
                    )
                    return redirect("order_history")
                return redirect("pay_order", order_id=held_order.id)

    return render(
        request,
        "store/checkout.html",
        {
            "form": form,
            "items": [
                {
                    "product": product,
                    "quantity": quantity,
                    "subtotal": product.price * quantity,
                }
                for product, quantity in products_to_order
            ],
            "total": total,
            "payment_configured": payment_configured,
        },
    )


@login_required
def pay_order(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
        payment_status=Order.PAYMENT_PENDING,
    )
    if order.payment_method != Order.PAYMENT_METHOD_RAZORPAY:
        messages.info(request, "Cash-on-delivery orders are paid when delivered.")
        return redirect("order_history")
    return render(
        request,
        "store/payment.html",
        {
            "order": order,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "amount_paise": int(order.total * 100),
            "payment_configured": bool(
                settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET
            ),
        },
    )


@login_required
@require_POST
def verify_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.payment_status == Order.PAYMENT_PAID:
        messages.info(request, f"Order #{order.id} has already been paid.")
        return redirect("order_history")
    if order.payment_status != Order.PAYMENT_PENDING:
        messages.error(request, "This order is no longer awaiting payment.")
        return redirect("order_history")
    if order.payment_method != Order.PAYMENT_METHOD_RAZORPAY:
        messages.error(request, "This order does not use online payment.")
        return redirect("order_history")

    payment_order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    if (
        not payment_order_id
        or not payment_id
        or not signature
        or payment_order_id != order.payment_gateway_order_id
    ):
        messages.error(request, "The payment response could not be verified.")
        return redirect("pay_order", order_id=order.id)

    client = get_razorpay_client()
    if client is None:
        messages.error(request, "Online payment is not configured. Contact the store.")
        return redirect("pay_order", order_id=order.id)

    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payment_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
    except SignatureVerificationError:
        logger.warning("Razorpay signature verification failed for order %s.", order.id)
        messages.error(
            request,
            "Payment verification failed. If money was deducted, contact the store before retrying.",
        )
        return redirect("pay_order", order_id=order.id)

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(id=order.id)
        if locked_order.payment_status == Order.PAYMENT_PAID:
            messages.info(request, f"Order #{order.id} has already been paid.")
            return redirect("order_history")
        if locked_order.payment_status != Order.PAYMENT_PENDING:
            messages.error(request, "This order is no longer awaiting payment.")
            return redirect("order_history")
        locked_order.payment_status = Order.PAYMENT_PAID
        locked_order.status = "Placed"
        locked_order.payment_id = payment_id
        locked_order.save(
            update_fields=["payment_status", "status", "payment_id"]
        )

    request.session["cart"] = {}
    messages.success(request, f"Payment received. Order #{order.id} is confirmed.")
    return redirect("order_history")


@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items__product").order_by("-created_at")
    return render(request, "store/order_history.html", {"orders": orders})

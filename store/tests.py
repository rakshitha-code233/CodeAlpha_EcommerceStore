from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from razorpay.errors import SignatureVerificationError
from unittest.mock import patch
from urllib.parse import urlencode

from .models import Category, Order, OrderItem, Product


class StorefrontTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Books")
        self.product = Product.objects.create(
            name="Django Guide",
            price="25.00",
            description="A practical web development guide",
            category=self.category,
            stock=5,
        )
        self.user = get_user_model().objects.create_user(
            username="shopper",
            password="test-password-123",
            email="shopper@example.com",
        )
        self.client.force_login(self.user)

    def test_catalog_search_category_and_sort(self):
        self.product.image_url = "https://images.example.com/django-guide.jpg"
        self.product.save(update_fields=["image_url"])
        Product.objects.create(
            name="Python Notes",
            price="10.00",
            description="Programming reference",
            category=self.category,
            stock=3,
        )
        hidden = Product.objects.create(
            name="Inactive item",
            price="1.00",
            description="Not for sale",
            stock=5,
            is_active=False,
        )

        response = self.client.get(
            reverse("product_list"),
            {"q": "guide", "category": self.category.id, "sort": "price_desc"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, "https://images.example.com/django-guide.jpg")
        self.assertContains(response, "THE EVERYDAY EDIT")
        self.assertContains(response, "Books")
        self.assertContains(response, "View product details")
        self.assertContains(response, "Buy now")
        self.assertContains(response, reverse("buy_now", args=[self.product.id]))
        self.assertNotContains(response, hidden.name)
        self.assertEqual(list(response.context["products"]), [self.product])

    def test_catalog_shows_all_product_categories_without_category_options(self):
        beauty = Category.objects.create(name="Beauty")
        Product.objects.create(
            name="Face Serum",
            price="18.00",
            description="Skin care serum",
            category=beauty,
            stock=4,
        )

        response = self.client.get(
            reverse("product_list"),
            {"category": self.category.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Beauty")
        self.assertContains(response, self.product.name)
        self.assertContains(response, "Face Serum")
        self.assertNotContains(response, 'aria-label="Shop by category"')
        self.assertNotContains(response, 'class="category-pill')
        self.assertNotContains(response, "SHOP BY CATEGORY")
        self.assertNotContains(
            response,
            f'href="{reverse("product_list")}?category={beauty.id}"',
        )

    def test_homepage_product_image_and_name_open_product_details(self):
        self.product.image_url = "https://images.example.com/django-guide.jpg"
        self.product.save(update_fields=["image_url"])

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'href="{reverse("product_detail", args=[self.product.id])}"',
        )
        self.assertContains(response, "https://images.example.com/django-guide.jpg")
        self.assertContains(response, "Add to cart")

    def test_demo_product_command_creates_categories_products_and_is_idempotent(self):
        call_command("seed_demo_products", verbosity=0)
        demo_categories = ("Beauty", "Dresses", "Stationery")
        first_product_count = Product.objects.filter(
            category__name__in=demo_categories
        ).count()
        first_category_count = Category.objects.filter(name__in=demo_categories).count()

        call_command("seed_demo_products", verbosity=0)

        self.assertEqual(first_product_count, 9)
        self.assertEqual(first_category_count, 3)
        self.assertEqual(
            Product.objects.filter(category__name__in=demo_categories).count(),
            first_product_count,
        )
        self.assertEqual(
            Category.objects.filter(name__in=demo_categories).count(),
            first_category_count,
        )
        for category_name in demo_categories:
            self.assertTrue(Category.objects.filter(name=category_name).exists())
        self.assertTrue(
            Product.objects.filter(
                name="Daily Glow Face Serum",
                image_url__startswith="https://images.unsplash.com/",
                stock__gt=0,
            ).exists()
        )
        self.assertTrue(
            Product.objects.filter(
                name="Daily Planner Journal",
                image_url__startswith="https://images.unsplash.com/photo-1456324504439-367cee3b3c32",
            ).exists()
        )

    def test_buy_now_adds_product_and_opens_checkout(self):
        self.client.force_login(self.user)
        url = reverse("buy_now", args=[self.product.id])

        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)

        self.assertRedirects(response, reverse("checkout"))
        self.assertEqual(self.client.session["cart"], {str(self.product.id): 1})

    def test_guest_must_sign_in_before_adding_or_buying(self):
        self.client.logout()
        product_url = reverse("product_detail", args=[self.product.id])
        login_link = f"{reverse('login')}?next={product_url}"
        login_url = (
            f"{reverse('login')}?{urlencode({'next': product_url})}"
        )

        storefront = self.client.get(reverse("product_list"))
        self.assertContains(storefront, ">Add to cart</a>")
        self.assertContains(storefront, ">Buy now</a>")
        self.assertContains(storefront, f'href="{login_link}"')
        self.assertNotContains(storefront, reverse("add_to_cart", args=[self.product.id]))
        self.assertNotContains(storefront, reverse("buy_now", args=[self.product.id]))

        detail = self.client.get(product_url)
        self.assertContains(detail, ">Add to cart</a>")
        self.assertContains(detail, ">Buy now</a>")
        self.assertContains(detail, f'href="{login_link}"')

        add_response = self.client.post(
            reverse("add_to_cart", args=[self.product.id]),
        )
        self.assertRedirects(add_response, login_url)

        buy_response = self.client.post(
            reverse("buy_now", args=[self.product.id]),
        )
        self.assertRedirects(buy_response, login_url)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_guest_checkout_redirects_to_login_and_preserves_cart(self):
        self.client.logout()
        session = self.client.session
        session["cart"] = {str(self.product.id): 1}
        session.save()

        response = self.client.get(reverse("checkout"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?{urlencode({'next': reverse('checkout')})}",
        )
        self.assertEqual(self.client.session["cart"], {str(self.product.id): 1})

    def test_guest_with_existing_cart_is_prompted_to_sign_in_before_checkout(self):
        self.client.logout()
        session = self.client.session
        session["cart"] = {str(self.product.id): 1}
        session.save()

        response = self.client.get(reverse("cart_detail"))

        self.assertContains(response, "Sign in to continue to checkout")
        self.assertContains(
            response,
            f'{reverse("login")}?next={reverse("checkout")}',
        )
        self.assertNotContains(response, "Continue to checkout")

    def test_product_detail_shows_related_products_and_stock(self):
        related = Product.objects.create(
            name="Python Notes",
            price="10.00",
            description="Programming reference",
            category=self.category,
            stock=3,
        )

        response = self.client.get(
            reverse("product_detail", args=[self.product.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "(5 available)")
        self.assertContains(response, "Product image coming soon")
        self.assertContains(response, related.name)

    def test_admin_product_list_previews_configured_image_urls(self):
        self.product.image_url = "https://images.example.com/django-guide.jpg"
        self.product.save(update_fields=["image_url"])
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin:store_product_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://images.example.com/django-guide.jpg")
        self.assertContains(response, "<img")

    def test_add_to_cart_requires_post_and_respects_stock(self):
        url = reverse("add_to_cart", args=[self.product.id])

        self.assertEqual(self.client.get(url).status_code, 405)
        for _ in range(5):
            self.client.post(url)
        self.client.post(url)

        self.assertEqual(self.client.session["cart"][str(self.product.id)], 5)

    def test_cart_quantity_update_and_remove(self):
        self.client.post(
            reverse("add_to_cart", args=[self.product.id]),
        )
        response = self.client.post(
            reverse("update_cart", args=[self.product.id]),
            {"quantity": "3"},
        )

        self.assertRedirects(response, reverse("cart_detail"))
        self.assertEqual(self.client.session["cart"][str(self.product.id)], 3)

        self.client.post(reverse("remove_from_cart", args=[self.product.id]))
        self.assertNotIn(str(self.product.id), self.client.session["cart"])

    @override_settings(
        RAZORPAY_KEY_ID="rzp_test_example",
        RAZORPAY_KEY_SECRET="test-secret",
    )
    def test_checkout_collects_shipping_and_verifies_payment(self):
        add_url = reverse("add_to_cart", args=[self.product.id])
        self.client.post(add_url)
        self.client.post(add_url)
        self.client.force_login(self.user)

        gateway_patch = patch("store.views.get_razorpay_client")
        gateway = gateway_patch.start()
        self.addCleanup(gateway_patch.stop)
        gateway_client = gateway.return_value
        gateway_client.order.create.return_value = {"id": "order_test_123"}

        response = self.client.get(reverse("checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order summary")
        self.assertEqual(Order.objects.count(), 0)

        response = self.client.post(
            reverse("checkout"),
            {
                "full_name": "Shopper Example",
                "email": "shopper@example.com",
                "phone": "1234567890",
                "address": "10 Main Street",
                "city": "Pune",
                "postal_code": "411001",
                "payment_method": Order.PAYMENT_METHOD_RAZORPAY,
            },
        )

        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("pay_order", args=[order.id]))
        self.assertEqual(order.total, 50)
        self.assertEqual(order.payment_status, Order.PAYMENT_PENDING)
        self.assertEqual(order.payment_gateway_order_id, "order_test_123")
        self.assertEqual(order.shipping_city, "Pune")
        self.assertEqual(OrderItem.objects.get(order=order).quantity, 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(self.client.session["cart"], {})

        payment_page = self.client.get(reverse("pay_order", args=[order.id]))
        self.assertContains(payment_page, "₹50.00")
        self.assertContains(payment_page, "order_test_123")
        gateway_client.utility.verify_payment_signature.return_value = None
        response = self.client.post(
            reverse("verify_payment", args=[order.id]),
            {
                "razorpay_order_id": "order_test_123",
                "razorpay_payment_id": "pay_test_456",
                "razorpay_signature": "valid-test-signature",
            },
        )

        self.assertRedirects(response, reverse("order_history"))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)
        self.assertEqual(order.payment_id, "pay_test_456")
        self.assertEqual(order.status, "Placed")
        self.assertEqual(self.client.session["cart"], {})
        gateway_client.utility.verify_payment_signature.assert_called_once()

    @override_settings(
        RAZORPAY_KEY_ID="rzp_test_example",
        RAZORPAY_KEY_SECRET="test-secret",
    )
    def test_invalid_payment_signature_does_not_confirm_order(self):
        self.client.post(reverse("add_to_cart", args=[self.product.id]))
        self.client.force_login(self.user)
        gateway_patch = patch("store.views.get_razorpay_client")
        gateway = gateway_patch.start()
        self.addCleanup(gateway_patch.stop)
        gateway.return_value.order.create.return_value = {"id": "order_test_123"}
        response = self.client.post(
            reverse("checkout"),
            {
                "full_name": "Shopper Example",
                "email": "shopper@example.com",
                "phone": "1234567890",
                "address": "10 Main Street",
                "city": "Pune",
                "postal_code": "411001",
                "payment_method": Order.PAYMENT_METHOD_RAZORPAY,
            },
        )
        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("pay_order", args=[order.id]))

        gateway.return_value.utility.verify_payment_signature.side_effect = (
            SignatureVerificationError("Invalid signature")
        )
        response = self.client.post(
            reverse("verify_payment", args=[order.id]),
            {
                "razorpay_order_id": "order_test_123",
                "razorpay_payment_id": "pay_test_456",
                "razorpay_signature": "invalid-signature",
            },
        )

        self.assertRedirects(response, reverse("pay_order", args=[order.id]))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_PENDING)
        self.assertEqual(order.payment_id, "")

    def test_checkout_without_razorpay_credentials_offers_cash_on_delivery(self):
        self.client.post(reverse("add_to_cart", args=[self.product.id]))
        self.client.force_login(self.user)

        response = self.client.get(reverse("checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cash on delivery")
        self.assertEqual(
            response.context["form"].fields["payment_method"].choices,
            [(Order.PAYMENT_METHOD_CASH_ON_DELIVERY, "Cash on delivery")],
        )
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    def test_cash_on_delivery_places_order_without_gateway_credentials(self):
        self.client.post(reverse("add_to_cart", args=[self.product.id]))
        self.client.post(reverse("add_to_cart", args=[self.product.id]))
        self.client.force_login(self.user)

        with patch("store.views.get_razorpay_client") as gateway:
            response = self.client.post(
                reverse("checkout"),
                {
                    "full_name": "Shopper Example",
                    "email": "shopper@example.com",
                    "phone": "1234567890",
                    "address": "10 Main Street",
                    "city": "Pune",
                    "postal_code": "411001",
                    "payment_method": Order.PAYMENT_METHOD_CASH_ON_DELIVERY,
                },
            )

        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse("order_history"))
        self.assertEqual(order.total, 50)
        self.assertEqual(order.status, "Placed")
        self.assertEqual(order.payment_status, Order.PAYMENT_PENDING)
        self.assertEqual(
            order.payment_method,
            Order.PAYMENT_METHOD_CASH_ON_DELIVERY,
        )
        self.assertEqual(order.payment_gateway_order_id, "")
        self.assertEqual(OrderItem.objects.get(order=order).quantity, 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(self.client.session["cart"], {})
        gateway.assert_not_called()

        self.assertRedirects(
            self.client.get(reverse("pay_order", args=[order.id])),
            reverse("order_history"),
        )
        self.assertRedirects(
            self.client.post(
                reverse("verify_payment", args=[order.id]),
                {
                    "razorpay_order_id": "fake-order",
                    "razorpay_payment_id": "fake-payment",
                    "razorpay_signature": "fake-signature",
                },
            ),
            reverse("order_history"),
        )
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_PENDING)

        history = self.client.get(reverse("order_history"))
        self.assertContains(history, "Cash on delivery")
        self.assertContains(history, "Pay when your order is delivered.")
        self.assertNotContains(history, "Continue payment")

    def test_checkout_rejects_quantity_above_current_stock(self):
        add_url = reverse("add_to_cart", args=[self.product.id])
        for _ in range(4):
            self.client.post(add_url)
        self.client.force_login(self.user)
        self.product.stock = 3
        self.product.save(update_fields=["stock"])

        response = self.client.post(
            reverse("checkout"),
            {
                "full_name": "Shopper Example",
                "email": "shopper@example.com",
                "phone": "1234567890",
                "address": "10 Main Street",
                "city": "Pune",
                "postal_code": "411001",
                "payment_method": Order.PAYMENT_METHOD_RAZORPAY,
            },
        )

        self.assertRedirects(response, reverse("cart_detail"))
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(self.client.session["cart"][str(self.product.id)], 4)

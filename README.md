# E-commerce Store (Django)

A responsive Django marketplace storefront with:
- Product catalog that displays active products across all categories, with search and price sorting
- Product detail pages with large product imagery, prices, and stock availability
- Session-based cart with quantity updates and stock checks
- Account registration, login, password reset, logout, and customer order history
- Shipping/contact checkout, order processing, cash on delivery, and optional Razorpay payment verification
- Admin management for categories, products, inventory, and orders
- SQLite database for products, categories, users, orders, and order items
- Responsive HTML/CSS storefront with JavaScript-powered Razorpay Checkout

## Requirements
- Python 3.11+
- Django 5.2.x
- Node.js is not required; the backend uses Django and Python.

## Setup (Windows PowerShell)

```powershell
cd C:\EcommerceStore
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open:
- Store: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/

## Deploying to Render

This project supports PostgreSQL in production and uses WhiteNoise to serve its
static files. Do not use the local SQLite database for a live deployment.

1. Push the project to a GitHub repository.
2. Create a PostgreSQL database and a Python web service in Render, connected to
   that repository.
3. Configure the web service:
   - **Build command:** `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - On plans with a pre-deploy command, set it to `python manage.py migrate`
     and use `gunicorn config.wsgi:application` as the start command.
   - On plans without a pre-deploy command, use
     `python manage.py migrate && gunicorn config.wsgi:application` as the
     start command so migrations run when the service starts.
4. Add these environment variables to the web service:
   - `SECRET_KEY`: a newly generated, private Django secret key.
   - `DEBUG`: `False`
   - `ALLOWED_HOSTS`: your service hostname, for example
     `your-store.onrender.com` (comma-separated if using multiple hosts).
   - `CSRF_TRUSTED_ORIGINS`: your full HTTPS site origin, for example
     `https://your-store.onrender.com`.
   - `DATABASE_URL`: the internal PostgreSQL connection URL provided by Render.
   - `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`: optional; use live credentials
     only when the site is ready to accept real payments.
   - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`,
     `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL`: SMTP settings required to
     deliver password reset links in production. Use an email provider's SMTP
     credentials or app password; keep credentials in Render environment
     variables, never in source control.
   - `SECURE_SSL_REDIRECT`: `True` once HTTPS is active. `SECURE_HSTS_SECONDS`
     can be set to a positive duration after HTTPS has been confirmed.
5. Once the service is deployed and migrations have run, create a Django
   superuser. If your plan provides a service shell, run
   `python manage.py createsuperuser` there. Otherwise, from a local checkout,
   set `DATABASE_URL` to the database's **external** connection URL in a
   PowerShell session and run:

   ```powershell
   $env:DATABASE_URL = "your external PostgreSQL URL"
   python manage.py createsuperuser
   Remove-Item Env:DATABASE_URL
   ```

   Do not save the database URL in source control. Sign in at `/admin/` to add
   categories and products.

Production settings fail at startup if `DEBUG=False` but `SECRET_KEY` or
`DATABASE_URL` is missing. Keep secrets in the host's environment-variable
settings, never in source control. Persistent media uploads are not configured;
product images should use publicly accessible image URLs.

Customer registration is available from the **Create account** link and
requires an email address so password recovery can work. Password reset links
are sent by email; configure SMTP environment variables on Render before
relying on password recovery. In local development, reset emails are printed
to the runserver console. The admin login also links to the same password
reset flow; an administrator can reset their password only if their account
has a working email address.

Sign in to the admin panel to add categories and products. Add as many product types and categories as needed; the storefront displays all active products together rather than filtering by category. Paste a publicly accessible, direct image URL in a product's image URL field; the admin product list shows an image preview. Products must be active and have available stock to be purchasable. Product images are fetched from their URL by the shopper's browser, so choose URLs that allow public viewing.

To add nine sample products across Beauty, Dresses, and Stationery with demo images, run:

```powershell
python manage.py seed_demo_products
```

The seed command is safe to rerun: it keeps existing sample products and does not overwrite prices, stock, or image URLs you have edited in the admin. Replace demo listings and image URLs with your own permitted product catalog before launch.

## Using the store

1. Create an account through **Create account**, or sign in.
2. Browse and search the product catalog, then open a product to see its details.
3. Add items to the cart, update quantities, and proceed to checkout.
4. Enter shipping details and choose **Cash on delivery** or **Razorpay** (when configured).
5. View placed orders and their payment status in **My Orders**. Manage products, inventory, and orders in the admin panel.

Run the storefront tests and Django's configuration check with:

```powershell
python manage.py check
python manage.py test store
```

## Razorpay test payments

Create a Razorpay account and get **test-mode** API keys from its dashboard. In the same PowerShell window that you use to run Django, set the keys before starting the server:

```powershell
$env:RAZORPAY_KEY_ID = "rzp_test_your_key_id"
$env:RAZORPAY_KEY_SECRET = "your_test_key_secret"
python manage.py runserver
```

Install the updated dependencies first when setting up a fresh environment:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
```

Customers can add products to their cart and enter shipping details. When Razorpay keys are configured, they can pay through Razorpay Checkout; the server verifies Razorpay's signature before confirming online orders. Inventory is reserved when an order is placed, and customers can resume pending Razorpay payments from **My Orders**. Use Razorpay's test credentials and test payment methods while developing. Never put the secret key in templates, JavaScript, source control, or a public repository.

Cash on delivery is available at checkout and works without payment-gateway credentials. The order is placed with payment marked pending; the customer pays the delivery person, and the store owner can update its payment status in the admin after collection. Razorpay online payment remains unavailable until valid keys are configured. A COD order does not charge a card or process an online payment.

Live payments require live-mode credentials, HTTPS, and production deployment/security configuration. Configure and test Razorpay webhooks and a process for releasing inventory from abandoned pending orders before going live. Product photos should be public image URLs you own or have permission to use; Google image-search results are not automatically licensed for reuse.

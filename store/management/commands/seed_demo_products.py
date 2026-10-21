from django.core.management.base import BaseCommand

from store.models import Category, Product


DEMO_PRODUCTS = (
    {
        "category": "Beauty",
        "name": "Daily Glow Face Serum",
        "price": "549.00",
        "description": "A lightweight daily face serum for a fresh, hydrated skincare routine.",
        "image_url": "https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?auto=format&fit=crop&w=900&q=85",
        "stock": 24,
    },
    {
        "category": "Beauty",
        "name": "Botanical Face Cream",
        "price": "399.00",
        "description": "A soft, nourishing face cream for your everyday self-care routine.",
        "image_url": "https://images.unsplash.com/photo-1556229010-6c3f2c9ca5f8?auto=format&fit=crop&w=900&q=85",
        "stock": 18,
    },
    {
        "category": "Beauty",
        "name": "Everyday Makeup Brush Set",
        "price": "699.00",
        "description": "A handy set of soft makeup brushes for simple everyday looks.",
        "image_url": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?auto=format&fit=crop&w=900&q=85",
        "stock": 15,
    },
    {
        "category": "Dresses",
        "name": "Floral Day Dress",
        "price": "1299.00",
        "description": "A comfortable floral dress for daytime outings and weekend plans.",
        "image_url": "https://images.unsplash.com/photo-1539008835657-9e8e9680c956?auto=format&fit=crop&w=900&q=85",
        "stock": 12,
    },
    {
        "category": "Dresses",
        "name": "Classic Evening Dress",
        "price": "1899.00",
        "description": "A versatile, elegant dress for dinners, celebrations, and special evenings.",
        "image_url": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?auto=format&fit=crop&w=900&q=85",
        "stock": 8,
    },
    {
        "category": "Dresses",
        "name": "Casual Weekend Dress",
        "price": "999.00",
        "description": "An easy-to-wear casual dress made for relaxed days and everyday comfort.",
        "image_url": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=900&q=85",
        "stock": 14,
    },
    {
        "category": "Stationery",
        "name": "Linen Cover Notebook",
        "price": "249.00",
        "description": "A pocket-friendly notebook for notes, lists, plans, and everyday ideas.",
        "image_url": "https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&w=900&q=85",
        "stock": 40,
    },
    {
        "category": "Stationery",
        "name": "Daily Planner Journal",
        "price": "349.00",
        "description": "A clean, easy-to-use journal to keep your schedule and goals in one place.",
        "image_url": "https://images.unsplash.com/photo-1456324504439-367cee3b3c32?auto=format&fit=crop&w=900&q=85",
        "stock": 28,
    },
    {
        "category": "Stationery",
        "name": "Pastel Desk Essentials Set",
        "price": "299.00",
        "description": "A cheerful stationery set for organising your desk, notes, and study sessions.",
        "image_url": "https://images.unsplash.com/photo-1517842645767-c639042777db?auto=format&fit=crop&w=900&q=85",
        "stock": 22,
    },
)


class Command(BaseCommand):
    help = "Add sample beauty, dress, and stationery products to the store."

    def handle(self, *args, **options):
        created_count = 0
        for item in DEMO_PRODUCTS:
            category, _ = Category.objects.get_or_create(name=item["category"])
            product, created = Product.objects.get_or_create(
                category=category,
                name=item["name"],
                defaults={
                    "price": item["price"],
                    "description": item["description"],
                    "image_url": item["image_url"],
                    "stock": item["stock"],
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
            else:
                self.stdout.write(
                    f"Keeping existing product: {product.name}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo catalog ready: {created_count} new products across Beauty, Dresses, and Stationery."
            )
        )

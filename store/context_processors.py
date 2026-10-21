def storefront_navigation(request):
    cart = request.session.get("cart", {})
    cart_quantity = 0
    if isinstance(cart, dict):
        for quantity in cart.values():
            try:
                cart_quantity += max(0, int(quantity))
            except (TypeError, ValueError):
                continue

    return {"cart_quantity": cart_quantity}

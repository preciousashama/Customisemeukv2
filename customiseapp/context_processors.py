from customiseapp.models import Wishlist
 
 
def header_counts(request):
    wish_count = 0
    if request.user.is_authenticated:
        wish_count = Wishlist.objects.filter(user=request.user).count()
 
    cart = request.session.get("cart", [])
    cart_count = sum(i.get("quantity", 1) for i in cart)
 
    return {
        "wish_count": wish_count,
        "cart_count": cart_count,
    }
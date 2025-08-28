# routers.py
from rest_framework.routers import DefaultRouter
from users.views import UsersViewSet, CartViewSet
router = DefaultRouter()
router.register(r'users', UsersViewSet, basename="users")
router.register(r'cart', CartViewSet, basename="cart" )

urlpatterns = router.urls

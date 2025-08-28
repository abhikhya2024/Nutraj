from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RegisterSerializer, LoginSerializer, EmailSerializer, OTPVerifySerializer, CartSerializer, CartItemSerializer, ProductSerializer
from drf_yasg.utils import swagger_auto_schema
from users.models import User, Cart, CartItem, Product
from rest_framework.parsers import MultiPartParser
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken
from drf_yasg import openapi
from django.core.mail import send_mail
from rest_framework.parsers import JSONParser, FormParser
from django.utils import timezone
import random
from django.shortcuts import get_object_or_404

class UsersViewSet(ModelViewSet):
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    parser_classes = [MultiPartParser]  # 👈 required for form-data upload
    def list(self, request, *args, **kwargs):
        users = self.get_queryset()
        serializer = self.get_serializer(users, many=True)
        return Response({
            "count": users.count(),
            "users": serializer.data
        })
    @swagger_auto_schema(
        request_body=RegisterSerializer,           # Tell Swagger what input to expect
        responses={201: "User registered successfully", 400: "Validation errors"}
    )

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User registered successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        request_body=LoginSerializer,
        responses={200: "Login successful", 400: "Invalid credentials"}
    )
    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "message": "Login successful"
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    @swagger_auto_schema(
        method="post",
        manual_parameters=[
            openapi.Parameter("receiver", openapi.IN_QUERY, description="Receiver email", type=openapi.TYPE_STRING),
            openapi.Parameter("subject", openapi.IN_QUERY, description="Email subject", type=openapi.TYPE_STRING),
            openapi.Parameter("message", openapi.IN_QUERY, description="Email message", type=openapi.TYPE_STRING),
        ],
        responses={200: "Email sent successfully", 400: "Failed to send email"}
    )
    @action(detail=False, methods=["post"], url_path="send-email",parser_classes=[JSONParser, FormParser, MultiPartParser] )
    def send_email_api(self, request):
        serializer = EmailSerializer(data=request.data)
        if serializer.is_valid():
            receiver = serializer.validated_data["receiver"]
            subject = serializer.validated_data["subject"]
            message = serializer.validated_data["message"]

            try:
                # 1️⃣ Find the user by email (receiver)
                try:
                    user = User.objects.get(email=receiver)
                except User.DoesNotExist:
                    return Response(
                        {"error": "User with this email does not exist"},
                        status=status.HTTP_404_NOT_FOUND
                    )

                # 2️⃣ Generate OTP and save it
                otp = f"{random.randint(100000, 999999)}"
                user.otp = otp
                user.otp_created_at = timezone.now()
                user.save()

                # 3️⃣ Append OTP to the message (optional)
                email_message = f"{message}\n\nYour OTP is: {otp}"

                # 4️⃣ Send the email
                send_mail(
                    subject,
                    email_message,
                    "abhikhya.ashi@gmail.com",  # Sender
                    [receiver],                # Recipient list
                    fail_silently=False,
                )

                return Response({"success": "Email with OTP sent successfully"})
            
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=["post"], url_path="verify-otp",parser_classes=[JSONParser, FormParser, MultiPartParser] )
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            otp = serializer.validated_data["otp"]

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            # OTP match check
            if user.otp != otp:
                return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

            # OTP expiry check (5 minutes)
            expiry_time = user.otp_created_at + timezone.timedelta(minutes=5)
            if timezone.now() > expiry_time:
                return Response({"error": "OTP expired"}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"success": "OTP verified successfully"}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CartViewSet(ModelViewSet):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer   # 👈 required

    def get_cart(self, user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    # GET /cart/
    @swagger_auto_schema(
        operation_summary="Get user cart",
        responses={200: CartSerializer()},
    )
    def list(self, request):
        cart = self.get_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    # POST /cart/add/
    @swagger_auto_schema(
        method="post",
        operation_summary="Add item to cart",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "product_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the product"),
                "quantity": openapi.Schema(type=openapi.TYPE_INTEGER, description="Quantity of product", default=1),
            },
            required=["product_id"],
        ),
        responses={200: "Item added to cart"},
    )
    @action(detail=False, methods=["post"])
    def add(self, request):
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))

        product = get_object_or_404(Product, id=product_id)
        cart = self.get_cart(request.user)

        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        if not created:
            cart_item.quantity += quantity
        else:
            cart_item.quantity = quantity
        cart_item.save()

        return Response({"message": "Item added to cart"}, status=status.HTTP_200_OK)

    # POST /cart/remove/
    @swagger_auto_schema(
        method="post",
        operation_summary="Remove item from cart",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "product_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of product"),
            },
            required=["product_id"],
        ),
        responses={200: "Item removed"},
    )
    @action(detail=False, methods=["post"])
    def remove(self, request):
        product_id = request.data.get("product_id")
        cart = self.get_cart(request.user)

        cart_item = CartItem.objects.filter(cart=cart, product_id=product_id).first()
        if cart_item:
            cart_item.delete()
            return Response({"message": "Item removed"})
        return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)

    # POST /cart/clear/
    @swagger_auto_schema(
        method="post",
        operation_summary="Clear cart",
        responses={200: "Cart cleared"},
    )
    @action(detail=False, methods=["post"])
    def clear(self, request):
        cart = self.get_cart(request.user)
        cart.items.all().delete()
        return Response({"message": "Cart cleared"})

    def partial_update(self, request, *args, **kwargs):
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))
        cart = self.get_cart(request.user)

        cart_item = CartItem.objects.filter(cart=cart, product_id=product_id).first()
        if not cart_item:
            return Response({"error": "Item not in cart"}, status=status.HTTP_404_NOT_FOUND)

        if quantity <= 0:
            cart_item.delete()
            return Response({"message": "Item removed from cart"})
        else:
            cart_item.quantity = quantity
            cart_item.save()
            return Response({"message": "Quantity updated", "quantity": cart_item.quantity})

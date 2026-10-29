from rest_framework import serializers
from django.contrib.auth import get_user_model
from tenants.models import Tenant
from recharge.models import RechargeRequest
from tokens.crypto import decrypt_token


class TenantRegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True, min_length=8)
    full_name = serializers.CharField(write_only=True)

    class Meta:
        model = Tenant
        fields = ("id", "meter_number", "registered_name", "phone_number", "email", "password", "full_name")
        read_only_fields = ("id",)

    def _unlinked_user_for_phone(self, phone_number):
        User = get_user_model()
        user = User.objects.filter(username__iexact=phone_number).first()
        if (
            user
            and not user.is_staff
            and not user.is_superuser
            and not hasattr(user, "tenant_profile")
        ):
            return user
        return None

    def validate_meter_number(self, value):
        if Tenant.objects.filter(meter_number=value).exists():
            raise serializers.ValidationError("A tenant with this meter number already exists.")
        return value

    def validate_phone_number(self, value):
        User = get_user_model()
        if Tenant.objects.filter(phone_number__iexact=value).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        if (
            User.objects.filter(username__iexact=value).exists()
            and not self._unlinked_user_for_phone(value)
        ):
            raise serializers.ValidationError("An account with this phone number already exists.")
        return value

    def validate_email(self, value):
        User = get_user_model()
        existing_email = User.objects.filter(email__iexact=value).first()
        phone_number = self.initial_data.get("phone_number", "")
        if existing_email and existing_email != self._unlinked_user_for_phone(phone_number):
            raise serializers.ValidationError("An account with this email address already exists.")
        return value

    def create(self, validated_data):
        email = validated_data.pop("email")
        password = validated_data.pop("password")
        full_name = validated_data.pop("full_name")
        User = get_user_model()
        user = self._unlinked_user_for_phone(validated_data["phone_number"])
        if user:
            user.email = email
            user.set_password(password)
            user.first_name = full_name
            user.save(update_fields=["email", "password", "first_name"])
        else:
            user = User.objects.create_user(
                username=validated_data["phone_number"],
                email=email,
                password=password,
                first_name=full_name,
            )
        return Tenant.objects.create(user=user, **validated_data)


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(
        max_length=254,
        trim_whitespace=True,
        error_messages={"blank": "Enter your phone number or email address."},
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=128,
        error_messages={"blank": "Enter your password."},
    )


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    otp = serializers.CharField(max_length=6)
    password = serializers.CharField(min_length=8, write_only=True)


class TenantSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.first_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Tenant
        fields = ("id", "full_name", "email", "meter_number", "registered_name", "phone_number",
                  "phone_verified_at", "verification_status", "rejection_reason")


class OTPVerifySerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    otp = serializers.CharField(max_length=6)


class LoginOTPVerifySerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    otp = serializers.CharField(max_length=6)


class RechargeCreateSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=100)

    def validate_tenant_id(self, value):
        try:
            tenant = Tenant.objects.get(id=value)
        except Tenant.DoesNotExist:
            raise serializers.ValidationError("Tenant not found.")
        if not tenant.phone_verified_at:
            raise serializers.ValidationError("Phone number must be verified first.")
        if tenant.verification_status != Tenant.VerificationStatus.APPROVED:
            raise serializers.ValidationError("Tenant must be approved before requesting a recharge.")
        return value


class RechargeStatusSerializer(serializers.ModelSerializer):
    meter_number = serializers.CharField(source="tenant.meter_number", read_only=True)
    token_available = serializers.SerializerMethodField()
    token = serializers.SerializerMethodField()

    def get_token_available(self, obj):
        return bool(obj.token_value_encrypted and obj.token_status == RechargeRequest.TokenStatus.FULFILLED)

    def get_token(self, obj):
        if not self.get_token_available(obj):
            return None
        return decrypt_token(bytes(obj.token_value_encrypted))

    class Meta:
        model = RechargeRequest
        fields = ("id", "amount", "payment_reference", "meter_number", "payment_status",
                  "token_status", "token_source", "token_available", "token", "paid_at",
                  "delivered_at", "created_at")


class RechargeCreateSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=100)

    def validate_tenant_id(self, value):
        try:
            tenant = Tenant.objects.get(id=value)
        except Tenant.DoesNotExist:
            raise serializers.ValidationError("Tenant not found.")
        if not tenant.phone_verified_at:
            raise serializers.ValidationError("Phone number must be verified first.")
        if tenant.verification_status != Tenant.VerificationStatus.APPROVED:
            raise serializers.ValidationError("Tenant must be approved before requesting a recharge.")
        return value

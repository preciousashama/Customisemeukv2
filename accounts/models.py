import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.conf import settings



class CustomUserManager(BaseUserManager):
    def _create_user(self, email: str, password: str, **extra):
        if not email:
            raise ValueError("Email address is required.")
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str = None, **extra):
        extra.setdefault("is_staff",     False)
        extra.setdefault("is_superuser", False)
        extra.setdefault("role",         CustomUser.Role.CUSTOMER)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str, **extra):
        extra["is_staff"]          = True
        extra["is_superuser"]      = True
        extra["is_active"]         = True
        extra["role"]              = CustomUser.Role.ADMIN
        extra["is_email_verified"] = True
        return self._create_user(email, password, **extra)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        ADMIN    = "admin",    "Admin"

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email      = models.EmailField(unique=True, db_index=True)
    full_name  = models.CharField(max_length=255, blank=True)
    role       = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    is_active          = models.BooleanField(default=False)
    is_staff           = models.BooleanField(default=False)
    is_email_verified  = models.BooleanField(default=False)

    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)
    last_login_ip         = models.GenericIPAddressField(null=True, blank=True)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until          = models.DateTimeField(null=True, blank=True)

    objects         = CustomUserManager()
    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name        = "user"
        verbose_name_plural = "users"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def record_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = timezone.now() + timedelta(minutes=30)
        self.save(update_fields=["failed_login_attempts", "locked_until"])

    def clear_failed_logins(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.save(update_fields=["failed_login_attempts", "locked_until"])


class EmailVerificationToken(models.Model):
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    token      = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used       = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"VerifyToken({self.user.email})"

    @property
    def is_expired(self):
        ttl = getattr(settings, "EMAIL_VERIFICATION_TIMEOUT_HOURS", 24)
        return timezone.now() > self.created_at + timedelta(hours=ttl)

    @property
    def is_valid(self):
        return not self.used and not self.is_expired


class PasswordResetToken(models.Model):
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token      = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used       = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ResetToken({self.user.email})"

    @property
    def is_expired(self):
        ttl = getattr(settings, "PASSWORD_RESET_TIMEOUT_HOURS", 2)
        return timezone.now() > self.created_at + timedelta(hours=ttl)

    @property
    def is_valid(self):
        return not self.used and not self.is_expired

import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()


class Command(BaseCommand):
    help = "Create a staff admin user for the CustomiseMe UK admin dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--email",    required=True)
        parser.add_argument("--name",     default="")
        parser.add_argument("--password", default=None)

    def handle(self, *args, **options):
        email     = options["email"].lower().strip()
        full_name = options["name"]
        password  = options["password"] or self._prompt()

        if not password:
            raise CommandError("Password cannot be empty.")

        try:
            user = User.objects.create_user(
                email             = email,
                password          = password,
                full_name         = full_name,
                role              = User.Role.ADMIN,
                is_staff          = True,
                is_active         = True,
                is_email_verified = True,
            )
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ Admin created → {user.email}\n"
                f"  Login at: /admin-login/\n"
            ))
        except IntegrityError:
            raise CommandError(f"An account with email '{email}' already exists.")

    def _prompt(self):
        pw1 = getpass.getpass("Password: ")
        pw2 = getpass.getpass("Confirm:  ")
        if pw1 != pw2:
            raise CommandError("Passwords do not match.")
        return pw1
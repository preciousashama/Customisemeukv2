from django.apps import AppConfig
 
 
class CustomiseappConfig(AppConfig):
    name               = "customiseapp"
    default_auto_field = "django.db.models.BigAutoField"
 
    def ready(self):
        # Import stripe_sync here — AFTER the full app registry is
        # initialised and DEFAULT_FILE_STORAGE is resolved to FirebaseStorage.
        # This is why the import must be here and not at module level.
        import customiseapp.stripe_sync  # noqa: F401
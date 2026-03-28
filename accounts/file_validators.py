import filetype
from django.core.exceptions import ValidationError




IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

DESIGN_ASSET_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "image/svg+xml",          
    "application/pdf",
    "application/zip",         
    "application/postscript", 
}

MAX_IMAGE_MB        = 8
MAX_DESIGN_ASSET_MB = 25



def _check_magic(uploaded_file, allowed_mimes, max_mb, label="File"):
    uploaded_file.seek(0)
    header = uploaded_file.read(261)
    uploaded_file.seek(0)

    kind = filetype.guess(header)

    if kind is None:
        ext = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else ""
        ct  = getattr(uploaded_file, "content_type", "") or ""
        if ext == "svg" and ("svg" in ct or "xml" in ct):
            detected_mime = "image/svg+xml"
        elif ext in ("ai", "eps") and ("postscript" in ct or "illustrator" in ct):
            detected_mime = "application/postscript"
        else:
            raise ValidationError(
                f"{label}: Could not determine file type. "
                f"Allowed formats: {', '.join(sorted(allowed_mimes))}."
            )
    else:
        detected_mime = kind.mime

    if detected_mime not in allowed_mimes:
        raise ValidationError(
            f"{label}: File type '{detected_mime}' is not allowed. "
            f"Please upload one of: {', '.join(sorted(allowed_mimes))}."
        )

    max_bytes = max_mb * 1024 * 1024
    if uploaded_file.size > max_bytes:
        raise ValidationError(
            f"{label}: File size {round(uploaded_file.size / (1024*1024), 1)} MB "
            f"exceeds the {max_mb} MB limit."
        )

    return detected_mime   # return detected MIME so caller can store it



def validate_product_image(uploaded_file):
    """Validates admin-uploaded product / carousel images."""
    return _check_magic(uploaded_file, IMAGE_MIMES, MAX_IMAGE_MB, label="Product image")


def validate_carousel_image(uploaded_file):
    return _check_magic(uploaded_file, IMAGE_MIMES, MAX_IMAGE_MB, label="Slide image")


def validate_design_asset(uploaded_file):
    return _check_magic(
        uploaded_file, DESIGN_ASSET_MIMES, MAX_DESIGN_ASSET_MB, label="Design file"
    )


def validate_multiple_design_assets(file_list, max_files=10):
    if len(file_list) > max_files:
        raise ValidationError(f"You may upload at most {max_files} files per submission.")
    results = []
    for f in file_list:
        mime = validate_design_asset(f)
        results.append((f, mime))
    return results
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_private_upload(upload) -> None:
    suffix = Path(upload.name).suffix.lower()
    if suffix not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError(
            _("This file type is not allowed. Allowed types: %(types)s"),
            params={"types": ", ".join(sorted(settings.ALLOWED_UPLOAD_EXTENSIONS))},
        )
    if upload.size > settings.MAX_UPLOAD_SIZE:
        limit_mb = settings.MAX_UPLOAD_SIZE // (1024 * 1024)
        raise ValidationError(
            _("The file is too large. The maximum size is %(size)s MB."),
            params={"size": limit_mb},
        )
    position = upload.tell() if hasattr(upload, "tell") else 0
    try:
        upload.seek(0)
        header = upload.read(16)
        if suffix == ".pdf" and not header.startswith(b"%PDF-"):
            raise ValidationError(_("The file content does not match a PDF file."))
        if suffix == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValidationError(_("The file content does not match a PNG image."))
        if suffix in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8\xff"):
            raise ValidationError(_("The file content does not match a JPEG image."))
        if suffix == ".txt":
            upload.seek(0)
            sample = upload.read(min(upload.size, 65536))
            if b"\x00" in sample:
                raise ValidationError(_("Text files cannot contain binary null bytes."))
            try:
                sample.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValidationError(_("Text files must use UTF-8 encoding.")) from exc
        if suffix == ".docx":
            upload.seek(0)
            try:
                with ZipFile(upload) as archive:
                    names = set(archive.namelist())
            except (BadZipFile, OSError) as exc:
                raise ValidationError(
                    _("The file content does not match a DOCX document.")
                ) from exc
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValidationError(_("The file content does not match a DOCX document."))
    finally:
        upload.seek(position)

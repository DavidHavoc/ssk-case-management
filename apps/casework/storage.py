from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateFileStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=None, base_url=None)

    @property
    def base_location(self) -> str:
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self) -> str:
        return str(Path(self.base_location).resolve())

    def path(self, name: str) -> str:
        resolved = Path(super().path(name)).resolve()
        root = Path(self.location).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("Invalid private file path.")
        return str(resolved)

    def url(self, name: str) -> str:
        raise ValueError("Private files do not have public URLs.")


private_file_storage = PrivateFileStorage()

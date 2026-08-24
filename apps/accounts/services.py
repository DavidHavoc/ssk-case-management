from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model

User = get_user_model()

ACCESS_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
ACCESS_CODE_GROUPS = 4
ACCESS_CODE_GROUP_LENGTH = 4


def generate_temporary_access_code() -> str:
    """Generate a readable code with over 90 bits of entropy."""
    groups = [
        "".join(secrets.choice(ACCESS_CODE_ALPHABET) for _ in range(ACCESS_CODE_GROUP_LENGTH))
        for _ in range(ACCESS_CODE_GROUPS)
    ]
    return "-".join(groups)


def issue_temporary_access_code(user: User) -> str:
    """Replace a user's password and require them to choose a private one."""
    code = generate_temporary_access_code()
    user.set_password(code)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])
    return code

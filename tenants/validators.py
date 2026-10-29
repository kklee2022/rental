from django.core.exceptions import ValidationError


def validate_prefix(value):
    normalized = (value or "").strip().upper()
    if not normalized:
        raise ValidationError("Prefix is required.")
    if len(normalized) > 12:
        raise ValidationError("Prefix must be at most 12 characters.")
    if not all(character.isalnum() or character == "-" for character in normalized):
        raise ValidationError("Prefix may contain letters, numbers and hyphens only.")
    if normalized[0] == "-":
        raise ValidationError("Prefix must start with a letter or number.")
    return normalized

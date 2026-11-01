"""AI Content Indicator.

Importing this package forces offline mode (HF_HUB_OFFLINE etc.) before any
model library can be imported anywhere in the application.
"""

from app import offline as _offline  # noqa: F401

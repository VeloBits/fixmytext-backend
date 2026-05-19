"""
Tool registration modules — organized by category.

Each sub-module exposes a ``register()`` function that registers its tools
with the central ``tool_registry._register()`` helper.  This package is
imported by ``tool_registry._register_all_tools()`` which calls each
module's ``register()`` in sequence.

To add a new tool category, create a new module here and import it below.
"""

from app.core.tools import ai

# Add future category modules here as they are extracted from tool_registry.py:
# from app.core.tools import case, cleanup, encoding, cipher, developer, text_tools

CATEGORY_MODULES = [
    ai,
    # case,
    # cleanup,
    # encoding,
    # cipher,
    # developer,
    # text_tools,
]


def register_all_categories() -> None:
    """Register tools from all category modules."""
    for module in CATEGORY_MODULES:
        module.register()

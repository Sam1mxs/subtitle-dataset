"""平台适配器；平台细节不进入公共管线。"""

from .base import ItemMetadata, ItemRef, SourceAdapter
from .local_http import LocalHttpAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "local-http": LocalHttpAdapter,
}

__all__ = ["ADAPTERS", "ItemMetadata", "ItemRef", "LocalHttpAdapter", "SourceAdapter"]

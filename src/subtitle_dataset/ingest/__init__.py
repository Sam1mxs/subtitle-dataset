"""数据发现、元数据解析与下载。"""

from .adapters import ADAPTERS, ItemMetadata, ItemRef, LocalHttpAdapter, SourceAdapter
from .collect import (
    CollectConfig,
    CollectedItem,
    CollectionReport,
    CollectionState,
    DownloadManager,
)
from .ratelimit import RateLimiter
from .sources import (
    DEFAULT_REGISTRY_PATH,
    LicenseStatus,
    SourceAuthorization,
    SourceRecord,
    SourceRegistry,
    check_authorization,
)

__all__ = [
    "ADAPTERS",
    "CollectedItem",
    "CollectionReport",
    "CollectionState",
    "CollectConfig",
    "DEFAULT_REGISTRY_PATH",
    "DownloadManager",
    "ItemMetadata",
    "ItemRef",
    "LicenseStatus",
    "LocalHttpAdapter",
    "RateLimiter",
    "SourceAdapter",
    "SourceAuthorization",
    "SourceRecord",
    "SourceRegistry",
    "check_authorization",
]

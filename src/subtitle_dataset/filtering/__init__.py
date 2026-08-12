"""字幕、文字、质量与安全过滤。"""

from .config import FilteringConfig
from .models import FrameDetection, PersistentBox, TextBox, TextRole, VideoSubtitleReport
from .policy import SampleTextDecision, SampleTextPolicy, check_frame_text_policy
from .text_regions import (
    HeuristicTextRegionDetector,
    TextRegionDetector,
    assign_geometric_roles,
)
from .tracking import track_boxes
from .video_filter import VideoSubtitleFilter

__all__ = [
    "FilteringConfig",
    "FrameDetection",
    "HeuristicTextRegionDetector",
    "PersistentBox",
    "SampleTextDecision",
    "SampleTextPolicy",
    "TextRegionDetector",
    "TextBox",
    "TextRole",
    "VideoSubtitleFilter",
    "VideoSubtitleReport",
    "assign_geometric_roles",
    "check_frame_text_policy",
    "track_boxes",
]

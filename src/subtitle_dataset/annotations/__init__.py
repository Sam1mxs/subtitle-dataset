"""bbox、polygon 与 mask 生成。"""

from .bbox import alpha_bbox
from .masks import alpha_to_inpaint_mask

__all__ = ["alpha_bbox", "alpha_to_inpaint_mask"]

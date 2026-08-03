"""输出图像与裁剪变换信息。"""

from __future__ import annotations

from pydantic import BaseModel

from .base import NonNegativeInt, PositiveInt

#: 裁剪矩形 [x, y, w, h]，基于原视频帧坐标
CropXywh = tuple[NonNegativeInt, NonNegativeInt, PositiveInt, PositiveInt]
#: 输出尺寸 [width, height]
TargetSize = tuple[PositiveInt, PositiveInt]


class ImageInfo(BaseModel):
    """最终输出图像的尺寸与文件 URI。"""

    width: PositiveInt
    height: PositiveInt
    clean_uri: str
    rendered_uri: str


class Transform(BaseModel):
    """裁剪与缩放变换。"""

    crop_xywh: CropXywh
    target_size: TargetSize

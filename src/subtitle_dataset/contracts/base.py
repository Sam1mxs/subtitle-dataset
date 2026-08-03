"""共享原语类型与枚举。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

#: 非负整数
NonNegativeInt = Annotated[int, Field(ge=0)]
#: 正整数
PositiveInt = Annotated[int, Field(gt=0)]
#: [0, 1] 区间浮点数
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
#: 64 位十六进制哈希字符串
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Split(StrEnum):
    """数据集划分。"""

    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class StageStatus(StrEnum):
    """处理阶段状态机。"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TimeBase(BaseModel):
    """有理数时间基，例如 ``{num: 1, den: 3000}`` 表示 1/3000 秒。"""

    num: PositiveInt
    den: PositiveInt

    def to_seconds(self, ticks: int) -> float:
        return ticks * self.num / self.den

    def ticks_to_ms(self, ticks: int) -> int:
        """将 ticks 换算为毫秒（四舍五入）。"""
        return round(ticks * self.num * 1000 / self.den)


class FrameRate(BaseModel):
    """ffprobe 报告的视频帧率信息。"""

    avg_num: NonNegativeInt
    avg_den: PositiveInt
    r_num: NonNegativeInt
    r_den: PositiveInt
    is_vfr: bool

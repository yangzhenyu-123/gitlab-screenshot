"""截图 DPI 预处理模块。

Playwright 输出的 PNG 无 DPI 元数据，python-docx 默认按 72 DPI 解释，
插入 Word 后可能模糊。本模块用 Pillow 重新保存图片，写入 DPI 元数据，
并按配置选择格式与质量。
"""
from pathlib import Path

from PIL import Image

from gitlabshot.config import Config


def preprocess_image(path, config: Config):
    """对截图进行 DPI 预处理，返回处理后的 Path。

    参数:
        path: 输入图片路径（pathlib.Path 或 str）
        config: Config 对象
    返回:
        处理后的图片 Path（若格式为 png 则原路径覆盖；若需转 jpeg 则生成新路径返回）
    """
    p = Path(path)

    img = Image.open(p)

    # JPEG 不支持 RGBA/调色板等模式，统一转 RGB
    if img.mode != "RGB":
        img = img.convert("RGB")

    dpi = (config.dpi, config.dpi)

    if config.image_format == "jpeg":
        new_path = p.with_suffix(".jpg")
        img.save(new_path, "JPEG", quality=config.quality, dpi=dpi)
        result = new_path
    else:
        # png 分支：直接覆盖原文件，PNG 忽略 quality
        img.save(p, "PNG", dpi=dpi)
        result = p

    return result

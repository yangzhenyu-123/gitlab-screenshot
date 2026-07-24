"""截图文件保存模块。

按命名规范将截图保存为文件：
    {包名}_{类型}{序号}.png
序号固定两位，从 01 开始递增（最大 99）。
"""
import shutil
from pathlib import Path
from typing import Iterable


def save_images(
    images: Iterable[Path],
    output_dir: Path,
    pkg_name: str,
    kind: str,
) -> list[str]:
    """将截图文件按命名规范保存到输出目录，返回已保存文件名列表。

    参数：
        images: 截图 Path 列表
        output_dir: 输出目录 Path
        pkg_name: 文件名前缀（包名）
        kind: 类型标识（master/baseline/release/tag/分支名）

    文件名格式：{pkg_name}_{kind}{NN}.png，NN 从 01 递增，上限 99。
    超过 99 张的截图将被忽略并打印警告。
    """
    saved: list[str] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for idx, img in enumerate(images, start=1):
        if idx > 99:
            print(f"警告：{kind} 类型截图超过 99 张，多余截图已忽略")
            break
        fname = f"{pkg_name}_{kind}{idx:02d}.png"
        dest = output_dir / fname
        # 移动截图到输出目录；跨文件系统时 shutil.move 会自动降级为复制+删除
        shutil.move(str(img), str(dest))
        saved.append(fname)
        print(f"  已保存：{dest}")
    return saved

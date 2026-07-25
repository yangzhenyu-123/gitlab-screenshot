"""配置文件加载模块。

支持通过 YAML 配置文件提供以下参数（命令行参数优先级高于配置文件）：
- project_url: GitLab 项目地址
- token: Personal Access Token
- baseline_tag: 基线 tag（用于「送测产品基线版本」截图）
- release_tag: 发布版本标签（用于「送测产品版本发布时间」截图）
- username / password: 网页登录凭证
- executable_path: Chromium 路径
- output_dir: 截图文件输出目录
- viewport / wait / max_screens 等截图参数

优先级：命令行显式参数 > 配置文件 > 环境变量 > 默认值。
若用户未安装 PyYAML，给出明确提示。
"""
from __future__ import annotations

from pathlib import Path


class ConfigFileError(Exception):
    """配置文件加载/解析错误。"""


def load_config_file(path: str) -> dict:
    """加载 YAML 配置文件，返回字典。文件不存在抛 ConfigFileError。"""
    p = Path(path)
    if not p.exists():
        raise ConfigFileError(f"配置文件不存在：{path}")
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise ConfigFileError(
            "未安装 PyYAML，无法加载配置文件。请执行 pip install pyyaml"
        ) from exc
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ConfigFileError(f"配置文件解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigFileError("配置文件顶层必须是字典/映射结构")
    return data

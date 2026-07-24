"""配置文件加载模块。

支持通过 YAML 配置文件提供以下参数（命令行参数优先级高于配置文件）：
- project_url: GitLab 项目地址
- token: Personal Access Token
- baseline_tag: 基线 tag（用于「送测产品基线版本」截图）
- release_tag: 发布版本标签（用于「送测产品版本发布时间」截图）
- username / password: 网页登录回退凭证
- executable_path: Chromium 路径
- output: 输出 docx 路径
- viewport / wait / max_screens 等截图参数

优先级：命令行显式参数 > 配置文件 > 默认值。
若用户未安装 PyYAML，给出明确提示。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional


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


def merge_config_file(
    cfg_dict: dict,
    *,
    project_url: Optional[str],
    token: Optional[str],
    output: Optional[str],
    username: Optional[str],
    password: Optional[str],
    executable_path: Optional[str],
    baseline_tag: Optional[str],
    release_tag: Optional[str],
) -> dict:
    """合并配置文件与命令行参数，命令行优先。

    返回合并后的字典，键与 cfg_dict 一致但已用命令行值覆盖。
    """
    merged = dict(cfg_dict)
    if project_url:
        merged["project_url"] = project_url
    if token:
        merged["token"] = token
    if output:
        merged["output"] = output
    if username:
        merged["username"] = username
    if password:
        merged["password"] = password
    if executable_path:
        merged["executable_path"] = executable_path
    if baseline_tag:
        merged["baseline_tag"] = baseline_tag
    if release_tag:
        merged["release_tag"] = release_tag
    return merged


def resolve_token(cfg: dict, cli_token: Optional[str], env_token: Optional[str]) -> str:
    """解析 token：命令行 > 配置文件 > 环境变量。"""
    if cli_token:
        return cli_token
    if cfg.get("token"):
        return str(cfg["token"])
    if env_token:
        return env_token
    return ""


def resolve_env_credential(cfg: dict, key: str, cli_val: Optional[str], env_val: Optional[str]) -> Optional[str]:
    """解析用户名/密码：命令行 > 配置文件 > 环境变量。"""
    if cli_val:
        return cli_val
    if cfg.get(key):
        return str(cfg.get(key))
    if env_val:
        return env_val
    return None

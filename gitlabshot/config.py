"""集中式配置数据类，封装所有可调参数及默认值。"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Config:
    """工具运行配置。所有字段均有默认值，可由 CLI 参数或环境变量覆盖。"""

    # ---- 目标 ----
    project_url: str = ""
    base_url: str = ""  # 如 https://gitlab.internal
    url_encoded_path: str = ""  # 如 group%2Fsubgroup%2Fproject
    project_path: str = ""  # 未编码路径，如 group/subgroup/project
    token: str = ""

    # ---- 视口与截图 ----
    viewport_width: int = 1440
    viewport_height: int = 900
    wait_ms: int = 800
    max_screens: int = 20
    keep_fixed: bool = False
    image_format: str = "png"  # png | jpeg
    quality: int = 85
    dpi: int = 96

    # ---- 文档 ----
    output_path: str = "audit.docx"
    continuous: bool = False
    margin_inches: float = 0.5

    # ---- 审计内容 ----
    branches: List[str] = field(default_factory=list)  # 指定分支，空则取所有分支
    context_tag: Optional[str] = None
    context_direction: str = "newer"  # newer | older

    # ---- 版本发布时间 / 产品基线 截图 ----
    # commits 类页面（/-/commits/<ref>）只截前几屏，默认 1 屏（约 3-5 个提交）
    commit_max_screens: int = 1
    # 产品基线参考标签：存在则取其 commit A 及之后 2 个 commit；不存在则取初始提交之后 2 个
    baseline_tag: str = "20250901_Release"

    # ---- 网页登录回退（token 方式失败时使用用户名+密码表单登录）----
    username: Optional[str] = None  # 显式用户名，覆盖 API 获取的 username
    password: Optional[str] = None  # 账号密码，用于表单登录回退

    # ---- 浏览器与网络 ----
    executable_path: Optional[str] = None
    ignore_https_errors: bool = True
    verify_ssl: bool = False  # GitLab API requests 是否校验 SSL

    def mask_token(self) -> str:
        """返回脱敏后的 token 字符串，用于日志输出。"""
        if not self.token:
            return "<empty>"
        if len(self.token) <= 4:
            return "***"
        return self.token[:4] + "***"

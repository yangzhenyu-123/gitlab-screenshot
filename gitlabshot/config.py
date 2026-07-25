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
    keep_fixed: bool = False  # 是否保留 GitLab 固定导航栏/侧边栏

    # ---- 文件输出 ----
    output_dir: str = "."          # 截图文件输出目录
    pkg_name: Optional[str] = None  # 文件名前缀（包名），默认取项目路径末段

    # ---- 审计内容 ----
    branches: List[str] = field(default_factory=list)  # 指定分支，空则取所有分支

    # ---- 版本发布时间 / 产品基线 截图 ----
    # commits 类页面（/-/commits/<ref>）只截前几屏，默认 1 屏（约 3-5 个提交）
    commit_max_screens: int = 1
    # commits 类页面单屏截图高度（像素），默认为视口高度的一半（450），
    # 只截视口顶部实现"减半高度"；不影响其它页面（master/tag/分支）的全局视口
    commit_viewport_height: int = 450
    # 产品基线参考标签：存在则取其 commit A 及之后第 2 个 commit
    baseline_tag: str = "20250901_Release"
    # 送测产品版本发布标签：截图 /-/commits/<release_tag>
    release_tag: Optional[str] = None

    # ---- 网页登录（用户名+密码表单登录，token 仅用于 API）----
    username: Optional[str] = None
    password: Optional[str] = None

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

"""GitLab 网页会话建立模块。

仅凭 Personal Access Token (PAT) 通过 GitLab 登录表单建立网页会话。
GitLab 官方支持将 PAT 作为密码用于网页登录：配合 gitlabshot.gitlab_api
先用 token 调用 /api/v4/user 获取用户名，再由本模块用「用户名 + token 作为
密码」提交登录表单完成会话建立。全程不输出 token 明文。
"""
import logging
from typing import Any, Optional, Type

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """GitLab 网页登录失败。"""


def mask_token(token: str) -> str:
    """返回脱敏后的 token 字符串，用于日志与错误输出。

    空字符串返回 "<empty>"；长度 <= 4 返回 "***"；否则返回前 4 位 + "***"。
    """
    if not token:
        return "<empty>"
    if len(token) <= 4:
        return "***"
    return token[:4] + "***"


def _playwright_timeout_error() -> Optional[Type[BaseException]]:
    """延迟导入 playwright 同步 API 的 TimeoutError，避免模块加载时硬依赖。

    沙箱/非运行环境可能未安装 playwright，此时返回 None。
    """
    try:
        from playwright.sync_api import TimeoutError
        return TimeoutError
    except ImportError:
        return None


def establish_session(page: Any, base_url: str, username: str, token: str) -> None:
    """通过 GitLab 登录表单建立网页会话。

    page 为 Playwright 同步 API 的 Page 对象；base_url 末尾斜杠会被去除。
    登录成功（当前 URL 不再含 /users/sign_in）后正常返回，失败抛 LoginError。
    """
    base = base_url.rstrip("/")
    sign_in_url = f"{base}/users/sign_in"
    logger.info("开始 GitLab 网页登录 username=%s token=%s", username, mask_token(token))

    timeout_error = _playwright_timeout_error()

    page.goto(sign_in_url)

    # 等待登录表单加载
    page.wait_for_selector("#user_login")
    page.wait_for_selector("#user_password")

    # 填充用户名与 token（作为密码）
    page.fill("#user_login", username)
    page.fill("#user_password", token)

    # 点击提交按钮：优先 #new_user 表单内提交按钮，回退到通用选择器
    for selector in (
        "#new_user input[type=submit]",
        "input[type=submit]",
        "button[type=submit]",
    ):
        try:
            page.click(selector)
            break
        except Exception as exc:
            # 选择器未找到/超时则尝试下一个，其它异常向上抛
            if timeout_error is not None and not isinstance(exc, timeout_error):
                raise
            continue
    else:
        raise LoginError("GitLab 网页登录失败：未找到登录表单提交按钮")

    # 等待跳转完成：容忍 networkidle 超时（某些 GitLab 版本存在长连接）
    try:
        page.wait_for_load_state("networkidle")
    except Exception as exc:
        if timeout_error is not None and not isinstance(exc, timeout_error):
            raise
        logger.debug("networkidle 等待超时，继续校验登录结果")

    # 校验登录成功：当前 URL 不含 /users/sign_in 即视为成功
    if "/users/sign_in" in page.url:
        raise LoginError(
            "GitLab 网页登录失败：登录后仍停留在登录页 "
            f"(username={username}, token={mask_token(token)})"
        )
    logger.info("GitLab 网页登录成功")

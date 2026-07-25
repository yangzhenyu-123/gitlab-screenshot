"""GitLab 网页会话建立模块。

仅通过「用户名 + 密码」提交 GitLab 登录表单建立网页会话。

内网 GitLab 实测：Personal Access Token (PAT) 无法用于网页表单登录
（较新版本 GitLab 拒绝把 PAT 当作表单密码，启用 2FA 的账号同样失败），
因此 PAT 只用于 API 调用，网页会话统一走用户名+密码表单登录。

全程不输出密码明文。
"""
import logging
from typing import Any, Optional, Type

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """GitLab 网页登录/会话建立失败。"""


def mask_token(token: str) -> str:
    """返回脱敏后的凭证字符串，用于日志与错误输出。

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


def establish_session_form(
    page: Any, base_url: str, username: str, credential: str, credential_kind: str = "password"
) -> None:
    """通过 GitLab 登录表单建立网页会话。

    page 为 Playwright 同步 API 的 Page 对象；base_url 末尾斜杠会被去除。
    以「用户名 + credential 作为密码」提交登录表单。credential_kind 用于
    日志标识（"password" 或 "token"）。登录成功（当前 URL 不再含
    /users/sign_in）后正常返回，失败抛 LoginError（含页面错误提示）。
    """
    base = base_url.rstrip("/")
    sign_in_url = f"{base}/users/sign_in"
    masked = mask_token(credential)
    logger.info(
        "表单登录 username=%s %s=%s", username, credential_kind, masked
    )

    timeout_error = _playwright_timeout_error()

    page.goto(sign_in_url)

    # 等待登录表单加载（兼容多版本选择器）
    login_selectors = ("#user_login", "input[name='user[login]']", "input#username")
    pwd_selectors = ("#user_password", "input[name='user[password]']", "input#password")
    login_sel = _first_visible(page, login_selectors)
    pwd_sel = _first_visible(page, pwd_selectors)
    if not login_sel or not pwd_sel:
        raise LoginError(
            "GitLab 网页登录失败：未找到登录表单字段（用户名或密码输入框）"
        )

    # 填充用户名与凭证（作为密码）
    page.fill(login_sel, username)
    page.fill(pwd_sel, credential)

    # 点击提交按钮：优先 #new_user 表单内提交按钮，回退到通用选择器
    submit_selectors = (
        "#new_user input[type=submit]",
        "#new_user button[type=submit]",
        "input[type=submit]",
        "button[type=submit]",
        "button[name='commit']",
    )
    submit_sel = _first_visible(page, submit_selectors)
    if not submit_sel:
        raise LoginError("GitLab 网页登录失败：未找到登录表单提交按钮")
    page.click(submit_sel)

    # 等待跳转完成：容忍 networkidle 超时（某些 GitLab 版本存在长连接）
    try:
        page.wait_for_load_state("networkidle")
    except Exception as exc:
        if timeout_error is not None and not isinstance(exc, timeout_error):
            raise
        logger.debug("networkidle 等待超时，继续校验登录结果")

    # 校验登录成功：当前 URL 不含 /users/sign_in 即视为成功
    if "/users/sign_in" in page.url:
        # 尝试读取页面错误提示，便于诊断
        alert = _read_alert(page)
        raise LoginError(
            "GitLab 网页登录失败：登录后仍停留在登录页 "
            f"(username={username}, {credential_kind}={masked})"
            + (f"，页面提示：{alert}" if alert else "")
        )
    logger.info("GitLab 表单登录成功")


def _first_visible(page: Any, selectors: tuple) -> Optional[str]:
    """返回第一个存在的选择器，均不存在返回 None。"""
    for sel in selectors:
        try:
            if page.is_visible(sel, timeout=2000):
                return sel
        except Exception:
            continue
    return None


def _read_alert(page: Any) -> str:
    """尝试读取登录页面的错误提示文本，失败返回空串。"""
    for sel in (
        ".flash-alert",
        ".alert-danger",
        ".flash-container .alert",
        "[role='alert']",
    ):
        try:
            text = page.inner_text(sel, timeout=1000).strip()
            if text:
                return text
        except Exception:
            continue
    return ""

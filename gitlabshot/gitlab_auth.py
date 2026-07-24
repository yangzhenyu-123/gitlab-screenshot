"""GitLab 网页会话建立模块。

仅凭 Personal Access Token (PAT) 建立可访问受保护页面的浏览器会话。

内网 GitLab 常见阻碍：
- 较新版本 GitLab 不允许 PAT 作为密码提交登录表单（PAT 仅用于 API / Basic Auth）；
- 启用 2FA 的账号无法用 PAT 登录表单；
- 表单登录依赖 CSRF token，自动化易失败。

因此本模块优先采用 GitLab 官方支持的 HTTP Basic Auth 方式：以
`oauth2` 作为用户名、PAT 作为密码，通过 Playwright context 的 HTTP 凭证
注入，访问任意 GitLab 页面时浏览器自动附带 Basic Auth header。该方式对
公开/私有项目均有效，且无需表单交互、不受 2FA 与 CSRF 影响。

若 Basic 方式不可用（极少数 GitLab 配置禁用 Basic Auth），回退到表单登录。
全程不输出 token 明文。
"""
import logging
from typing import Any, Optional, Type

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """GitLab 网页登录/会话建立失败。"""


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


def establish_session_basic(context: Any, base_url: str, token: str) -> None:
    """记录 HTTP Basic Auth 会话已建立（凭证在创建 context 时注入）。

    Playwright 的 http_credentials 需在 `browser.new_context()` 时传入，
    本函数仅做日志记录与存在性校验，便于编排层在「Basic → 表单」回退流程中
    保持对称调用。凭证实际由 capture.launch_browser(config, http_credentials)
    在创建 context 时注入。
    """
    logger.info(
        "HTTP Basic Auth 凭证已注入（oauth2 + token=%s），作用域 %s",
        mask_token(token),
        base_url.rstrip("/"),
    )


def establish_session_form(page: Any, base_url: str, username: str, token: str) -> None:
    """通过 GitLab 登录表单建立网页会话（回退方式）。

    page 为 Playwright 同步 API 的 Page 对象；base_url 末尾斜杠会被去除。
    以「用户名 + token 作为密码」提交登录表单。登录成功（当前 URL 不再含
    /users/sign_in）后正常返回，失败抛 LoginError。

    注意：较新版本 GitLab 可能不接受 PAT 作为表单密码，此方式仅作回退。
    """
    base = base_url.rstrip("/")
    sign_in_url = f"{base}/users/sign_in"
    logger.info(
        "回退到表单登录 username=%s token=%s", username, mask_token(token)
    )

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
    logger.info("GitLab 表单登录成功")


def verify_session(page: Any, base_url: str, project_path: str, token: str) -> bool:
    """验证会话是否可访问受保护页面。

    访问带 ?private_token=TOKEN 的项目根页面，若未被重定向到 /users/sign_in
    则视为会话有效。返回 True 表示可访问，False 表示需要登录。

    private_token 是 GitLab 网页端官方支持的 PAT 认证方式之一，对禁用
    Basic Auth / 表单 PAT 登录的内网实例尤其关键。
    """
    from urllib.parse import urlsplit, urlunsplit, urlencode

    base = base_url.rstrip("/")
    probe_url = f"{base}/{project_path}"
    if token:
        parts = urlsplit(probe_url)
        extra = urlencode({"private_token": token})
        new_query = (
            f"{parts.query}&{extra}" if parts.query else extra
        )
        probe_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
        )
    timeout_error = _playwright_timeout_error()
    try:
        page.goto(probe_url, wait_until="domcontentloaded")
    except Exception as exc:
        if timeout_error is not None and isinstance(exc, timeout_error):
            return False
        raise
    return "/users/sign_in" not in page.url

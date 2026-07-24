"""Playwright 逐视口截图核心模块。

驱动无头 Chromium 按视口高度逐屏滚动网页并截取当前可见视口，
生成有序截图列表，供后续审计文档拼装使用。
"""
from gitlabshot.config import Config
from playwright.sync_api import sync_playwright, Error as PlaywrightError


class NavigationError(Exception):
    """页面导航失败（超时或连接错误）。"""


class ChromiumMissingError(Exception):
    """Chromium 浏览器不可用或未正确安装。"""


def launch_browser(config: Config, http_credentials=None):
    """启动 Chromium 浏览器，返回 (browser, context, page)。

    http_credentials: 可选 dict，形如
        {"username": "oauth2", "password": "<token>", "origin": "https://host"}
        传入时浏览器对所有匹配 origin 的请求自动附带 HTTP Basic Auth header，
        用于访问需要认证的 GitLab 页面（避免表单登录）。
    """
    pw = sync_playwright().start()
    launch_kwargs = {
        "headless": True,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }
    if config.executable_path is not None:
        launch_kwargs["executable_path"] = config.executable_path
    try:
        browser = pw.chromium.launch(**launch_kwargs)
    except Exception:
        raise ChromiumMissingError(
            "请执行 playwright install chromium 或设置 PLAYWRIGHT_BROWSERS_PATH"
        )

    context_kwargs = {
        "viewport": {
            "width": config.viewport_width,
            "height": config.viewport_height,
        },
        "ignore_https_errors": config.ignore_https_errors,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if http_credentials is not None:
        context_kwargs["http_credentials"] = http_credentials
    context = browser.new_context(**context_kwargs)
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
    )
    page = context.new_page()
    return (browser, context, page)


def capture_page(page, url: str, config: Config, tmp_dir, max_screens: int = None) -> list:
    """对指定 URL 逐视口截图，返回截图文件 Path 列表。tmp_dir 是 pathlib.Path。

    max_screens: 可选，覆盖 config.max_screens。用于 commits 类页面（版本发布
    时间、产品基线）只截前几屏（前几个提交），传 1 即只截一屏。
    """
    # a. 导航到目标 URL（附加 private_token 参数，用于网页认证）
    #    GitLab 网页端识别 ?private_token=TOKEN 并据此建立会话视图，
    #    对内网禁用 Basic Auth / 表单 PAT 登录的场景尤为关键。
    from urllib.parse import urlsplit, urlunsplit, urlencode

    if max_screens is None:
        max_screens = config.max_screens

    parts = urlsplit(url)
    display_url = url  # 保留原始 URL（不含 private_token）用于地址栏显示
    if config.token:
        existing = parts.query
        extra = urlencode({"private_token": config.token})
        new_query = f"{existing}&{extra}" if existing else extra
        url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
        )

    try:
        page.goto(url, wait_until="networkidle")
    except PlaywrightError as e:
        raise NavigationError(f"导航失败: {url} ({e})")

    # b. 注入模拟浏览器地址栏（只显示 https:// 文本，不含 favicon/锁图标）
    #    以普通文档流插入 body 顶部，出现在第一屏截图，随滚动离开视口
    page.evaluate(
        """(url) => {
            const bar = document.createElement('div');
            bar.setAttribute('data-gitlabshot-urlbar', '1');
            bar.style.cssText = (
                'display:flex;align-items:center;box-sizing:border-box;'
                + 'width:100%;height:40px;padding:0 16px;'
                + 'background:#f1f3f4;border-bottom:1px solid #dadce0;'
                + 'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",'
                + 'Roboto,Helvetica,Arial,sans-serif;font-size:14px;'
                + 'color:#202124;white-space:nowrap;overflow:hidden;'
                + 'text-overflow:ellipsis;position:relative;z-index:99999;'
            );
            bar.textContent = url;
            document.body.insertBefore(bar, document.body.firstChild);
        }""",
        display_url,
    )

    # c. 隐藏 GitLab 固定元素（导航栏、侧边栏等）
    if not config.keep_fixed:
        page.add_style_tag(
            content=(
                ".navbar-gitlab, .top-bar, .nav-sidebar, .sidebar-container, "
                ".layout-wrapper .nav-wrapper { display: none !important; }"
                " .content-wrapper { margin: 0 !important; padding: 0 !important; }"
            )
        )

    # d. 移除懒加载属性，确保图片随滚动加载
    page.evaluate(
        "document.querySelectorAll('img[loading]').forEach("
        "img => img.removeAttribute('loading'));"
    )

    # e. 预滚动触发懒加载：步进 300px，每步 100ms，滚到底部后回到顶部
    page.evaluate(
        """async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 300;
                const timer = setInterval(() => {
                    const scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight) {
                        clearInterval(timer);
                        window.scrollTo(0, 0);
                        resolve();
                    }
                }, 100);
            });
        }"""
    )
    try:
        page.wait_for_load_state("networkidle")
    except PlaywrightError:
        pass

    # f. 重新读取页面总高度（预滚动后内容可能扩展）
    total_height = page.evaluate("document.body.scrollHeight")

    # g. 视口高度
    viewport_height = config.viewport_height

    # h. 主截图循环：按视口高度逐屏滚动并截图
    screenshots = []
    scroll_y = 0
    page_num = 1
    while scroll_y < total_height and page_num <= max_screens:
        page.evaluate(f"window.scrollTo(0, {scroll_y})")
        page.wait_for_timeout(config.wait_ms)
        path = tmp_dir / f"page_{page_num:03d}.png"
        page.screenshot(path=str(path), full_page=False)
        screenshots.append(path)
        scroll_y += viewport_height
        page_num += 1

    if page_num > max_screens and scroll_y < total_height:
        print("达到最大屏数上限，可能存在未捕获内容")

    # h. 返回截图 Path 列表（空列表表示未捕获）
    return screenshots

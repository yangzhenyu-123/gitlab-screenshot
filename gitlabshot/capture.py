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


def launch_browser(config: Config):
    """启动 Chromium 浏览器，返回 (browser, context, page)。"""
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

    context = browser.new_context(
        viewport={
            "width": config.viewport_width,
            "height": config.viewport_height,
        },
        ignore_https_errors=config.ignore_https_errors,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
    )
    page = context.new_page()
    return (browser, context, page)


def capture_page(page, url: str, config: Config, tmp_dir) -> list:
    """对指定 URL 逐视口截图，返回截图文件 Path 列表。tmp_dir 是 pathlib.Path。"""
    # a. 导航到目标 URL
    try:
        page.goto(url, wait_until="networkidle")
    except PlaywrightError as e:
        raise NavigationError(f"导航失败: {url} ({e})")

    # b. 隐藏 GitLab 固定元素（导航栏、侧边栏等）
    if not config.keep_fixed:
        page.add_style_tag(
            content=(
                ".navbar-gitlab, .top-bar, .nav-sidebar, .sidebar-container, "
                ".layout-wrapper .nav-wrapper { display: none !important; }"
                " .content-wrapper { margin: 0 !important; padding: 0 !important; }"
            )
        )

    # c. 移除懒加载属性，确保图片随滚动加载
    page.evaluate(
        "document.querySelectorAll('img[loading]').forEach("
        "img => img.removeAttribute('loading'));"
    )

    # d. 预滚动触发懒加载：步进 300px，每步 100ms，滚到底部后回到顶部
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

    # e. 重新读取页面总高度（预滚动后内容可能扩展）
    total_height = page.evaluate("document.body.scrollHeight")

    # f. 视口高度
    viewport_height = config.viewport_height

    # g. 主截图循环：按视口高度逐屏滚动并截图
    screenshots = []
    scroll_y = 0
    page_num = 1
    while scroll_y < total_height and page_num <= config.max_screens:
        page.evaluate(f"window.scrollTo(0, {scroll_y})")
        page.wait_for_timeout(config.wait_ms)
        path = tmp_dir / f"page_{page_num:03d}.png"
        page.screenshot(path=str(path), full_page=False)
        screenshots.append(path)
        scroll_y += viewport_height
        page_num += 1

    if page_num > config.max_screens and scroll_y < total_height:
        print("达到最大屏数上限，可能存在未捕获内容")

    # h. 返回截图 Path 列表（空列表表示未捕获）
    return screenshots

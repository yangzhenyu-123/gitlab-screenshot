"""Playwright 逐视口截图核心模块。

驱动无头 Chromium 按视口高度逐屏滚动网页并截取当前可见视口，
生成有序截图列表，供后续审计文档拼装使用。
"""
from gitlabshot.config import Config
from playwright.sync_api import sync_playwright, Error as PlaywrightError


# 生成强制布局修正 JS：隐藏侧边栏后，面包屑与主内容对齐并尽量左移。
# GitLab 16+ super sidebar 是运行时 JS 组件，会在导航/滚动/resize 后动态重写
# 容器 inline style（padding-left、top-bar left），绕过 CSS specificity。因此
# 放弃清零占位的对抗思路（会被运行时覆盖），改用 transform: translateX 平移：
# - 读面包屑与 main 的运行时实际 x
# - 算到目标左缘（target_x）的偏移量，各自 translateX 平移
# - 同时扩展 main 宽度铺满到视口右缘，避免平移后右侧留白
# - transform 是合成层属性，GitLab 运行时不管理它，不会被覆盖
# 在导航后与每次截图前各执行一次，应对滚动中坐标变化。
def _force_layout_js(target_x: int) -> str:
    return """() => {
    const TARGET_X = """ + str(target_x) + """;
    const vw = document.documentElement.clientWidth || window.innerWidth;
    const bc = document.querySelector(
        '.gl-breadcrumbs, .breadcrumbs-container, .breadcrumbs, '
        + '[data-testid="breadcrumb"]'
    );
    const main = document.querySelector('main')
        || document.querySelector('[role="main"]');
    if (bc) {
        const bcX = Math.round(bc.getBoundingClientRect().x);
        const bcDx = TARGET_X - bcX;
        if (bcDx !== 0) {
            bc.style.setProperty('transform', 'translateX(' + bcDx + 'px)', 'important');
        }
    }
    if (main) {
        const mainX = Math.round(main.getBoundingClientRect().x);
        const mainDx = TARGET_X - mainX;
        if (mainDx !== 0) {
            main.style.setProperty('transform', 'translateX(' + mainDx + 'px)', 'important');
        }
        // 平移后右侧留白：扩展宽度铺满到视口右缘
        main.style.setProperty('width', (vw - TARGET_X) + 'px', 'important');
        main.style.setProperty('max-width', (vw - TARGET_X) + 'px', 'important');
    }
}"""


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


def capture_page(page, url: str, config: Config, tmp_dir, max_screens: int = None, inject_urlbar: bool = True, shot_height: int = None, target_x: int = 16) -> list:
    """对指定 URL 逐视口截图，返回截图文件 Path 列表。tmp_dir 是 pathlib.Path。

    max_screens: 可选，覆盖 config.max_screens。用于 commits 类页面（版本发布
    时间、产品基线）只截前几屏（前几个提交），传 1 即只截一屏。
    inject_urlbar: 是否注入模拟浏览器地址栏（显示 https:// 文本）。地址栏用
        fixed 定位，每屏截图都可见；commits 类页面传 False 保留 GitLab 原生
        面包屑路径、不注入地址栏。
    shot_height: 可选，单屏截图高度（像素）。默认用 config.viewport_height 截
    整个视口；commits 类页面传较小值（如 450）只截视口顶部，实现"减半高度"
    而不影响其它页面的全局视口。同时作为滚动步长，确保连续截图无遗漏。
    target_x: 左移目标 x 坐标（像素）。面包屑与主内容平移到此 x，默认 16。
    master 等页面可传较大值（如 48）增加左边距。
    """
    # a. 导航到目标 URL（网页会话由表单登录的 cookie 维持）
    if max_screens is None:
        max_screens = config.max_screens

    display_url = url

    # 打印仓库地址之后的完整路径，便于确认
    print(f"  访问路径：{display_url}")

    try:
        page.goto(url, wait_until="domcontentloaded")
    except PlaywrightError as e:
        raise NavigationError(
            f"导航失败: {display_url}（原因：{e}）"
        )

    # b. 注入模拟浏览器地址栏（只显示 https:// 文本，不含 favicon/锁图标）
    #    用 fixed 定位固定在视口顶部，每屏截图都可见；第一屏在地址栏下方
    #    还能看到 GitLab 原生面包屑，后续屏面包屑滚出视口只剩地址栏。
    #    inject_urlbar=False 时跳过（如 commits 页只保留 GitLab 原生面包屑路径）
    if inject_urlbar:
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
                    + 'text-overflow:ellipsis;'
                    + 'position:fixed;top:0;left:0;z-index:99999;'
                );
                bar.textContent = url;
                document.body.insertBefore(bar, document.body.firstChild);
            }""",
            display_url,
        )

    # c. 隐藏 GitLab 左侧导航侧边栏，面包屑与主内容对齐并尽量左移
    #    兼容多版本侧边栏类名：
    #    - 旧版（≤15）：.nav-sidebar / .sidebar-container
    #    - 新版（16+ 超级侧边栏）：.super-sidebar / aside[class*="sidebar"]
    #    aside[class*="sidebar"] 只命中带 sidebar 类的 <aside>，不误伤主内容区
    #
    #    左移策略：放弃对抗 GitLab 运行时（它会重写容器 padding/top-bar left），
    #    改用 transform: translateX 把面包屑与 main 各自平移到目标左缘（视口左缘
    #    + 16px 留白）。transform 是合成层属性，运行时不管理，不会被覆盖。
    #    每次截图前重执行以应对滚动中变化。
    if not config.keep_fixed:
        page.add_style_tag(
            content=(
                # 左侧导航侧边栏：精确命中，不误伤右侧项目信息面板
                ".nav-sidebar, .sidebar-container, .super-sidebar, "
                ".super-sidebar-content, "
                "[data-testid=\"super-sidebar\"] { display: none !important; }"
            )
        )
        page.evaluate(_force_layout_js(target_x))

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
        page.wait_for_load_state("domcontentloaded")
    except PlaywrightError:
        pass

    # f. 重新读取页面总高度（预滚动后内容可能扩展）
    total_height = page.evaluate("document.body.scrollHeight")

    # g. 视口高度与截图高度
    #    shot_height 用于 commits 类页面截取视口顶部一部分（减半高度效果），
    #    同时作为滚动步长；默认等于视口全高
    viewport_height = config.viewport_height
    if shot_height is None:
        shot_height = viewport_height

    # h. 主截图循环：按截图高度逐屏滚动并截图
    #    每次截图前重新执行布局修正，覆盖 GitLab 运行时在滚动中重写的 inline style
    screenshots = []
    scroll_y = 0
    page_num = 1
    while scroll_y < total_height and page_num <= max_screens:
        page.evaluate(f"window.scrollTo(0, {scroll_y})")
        page.wait_for_timeout(config.wait_ms)
        if not config.keep_fixed:
            page.evaluate(_force_layout_js(target_x))
        path = tmp_dir / f"page_{page_num:03d}.png"
        # shot_height < viewport 时用 clip 只截视口顶部 shot_height 区域
        if shot_height < viewport_height:
            page.screenshot(
                path=str(path), full_page=False,
                clip={"x": 0, "y": 0, "width": config.viewport_width, "height": shot_height},
            )
        else:
            page.screenshot(path=str(path), full_page=False)
        screenshots.append(path)
        scroll_y += shot_height
        page_num += 1

    if page_num > max_screens and scroll_y < total_height:
        print("达到最大屏数上限，可能存在未捕获内容")

    # h. 返回截图 Path 列表（空列表表示未捕获）
    return screenshots

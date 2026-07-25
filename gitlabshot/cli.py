"""GitLab 仓库审计截图工具 CLI 入口与主编排模块。

串联 config / config_loader / gitlab_api / gitlab_auth / capture / saver
各模块，按「主线 → 送测产品基线版本 → 送测产品版本发布时间 → 送测产品版本标签 → 分支」
顺序逐屏截图，并按命名规范直接保存为 PNG 文件。

退出码：
    0  成功
    1  参数错误（缺 URL/token/用户名密码）
    2  项目不可达
    3  未捕获任何截图
    4  Chromium 缺失
    5  token 无效或登录失败
"""
import argparse
import os
import shutil
import tempfile
import urllib.parse
from pathlib import Path

from gitlabshot.config import Config
from gitlabshot.gitlab_api import (
    APIError,
    GitLabAPIClient,
    InvalidTokenError,
    TagNotFoundError,
)
from gitlabshot.gitlab_auth import LoginError, establish_session_form
from gitlabshot.capture import (
    ChromiumMissingError,
    NavigationError,
    capture_page,
    launch_browser,
)
from gitlabshot.saver import save_images


def parse_project_url(url: str) -> tuple[str, str, str]:
    """解析 GitLab 项目地址，返回 (base_url, project_path, url_encoded_path)。

    兼容网页 URL 与 clone 地址（末尾带 .git 后缀会被剥离）：
        https://gitlab.internal/group/subgroup/project
        https://gitlab.internal/group/subgroup/project.git
    均解析为：
        base_url = https://gitlab.internal
        project_path = group/subgroup/project
        url_encoded_path = group%2Fsubgroup%2Fproject
    """
    parts = urllib.parse.urlsplit(url)
    base_url = f"{parts.scheme}://{parts.netloc}"
    project_path = parts.path.strip("/")
    # 剥离 clone 地址末尾的 .git 后缀（GitLab API 与网页 URL 均不含该后缀）
    if project_path.lower().endswith(".git"):
        project_path = project_path[: -len(".git")]
    url_encoded_path = urllib.parse.quote(project_path, safe="")
    return base_url, project_path, url_encoded_path


def main() -> int:
    """CLI 主函数，返回退出码。"""
    parser = argparse.ArgumentParser(
        prog="gitlabshot",
        description="GitLab 仓库审计逐屏截图工具（PNG 文件输出）",
    )
    parser.add_argument("project_url", nargs="?", help="GitLab 项目地址")
    parser.add_argument(
        "--config",
        default=None,
        help="YAML 配置文件路径（提供 project_url/token/baseline_tag/release_tag 等）",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Personal Access Token（或环境变量 GITLABSHOT_TOKEN）",
    )
    parser.add_argument(
        "-o", "--output-dir", default=".", help="截图文件输出目录（默认当前目录）"
    )
    parser.add_argument(
        "--pkg-name", default=None, help="文件名前缀（包名），默认取项目路径末段"
    )
    parser.add_argument(
        "--viewport", default="1440x900", help="视口尺寸，格式 WxH"
    )
    parser.add_argument("--wait", type=int, default=800, help="每屏等待毫秒")
    parser.add_argument("--max-screens", type=int, default=20, help="最大屏数")
    parser.add_argument(
        "--keep-fixed", action="store_true", help="保留 GitLab 固定元素"
    )
    parser.add_argument(
        "--branch", action="append", default=None, help="指定分支（可多次）"
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="只截指定类型（master/baseline/release/tag），可逗号分隔或多次传入；"
        "不传则全截。指定后未列出的类型及分支截图将被跳过",
    )
    parser.add_argument(
        "--executable-path", default=None, help="指定 Chromium 路径"
    )
    parser.add_argument(
        "--baseline-tag",
        default=None,
        help="产品基线参考标签（取其 commit A 后第2个 commit C 截图）；可由配置文件提供",
    )
    parser.add_argument(
        "--release-tag",
        default=None,
        help="送测产品版本发布标签（截图 /-/commits/<release_tag>）；可由配置文件提供",
    )
    parser.add_argument(
        "--commit-screens",
        type=int,
        default=1,
        help="版本发布时间/产品基线 commits 页面截图屏数（默认1，只截前几个提交）",
    )
    parser.add_argument(
        "--commit-viewport-height",
        type=int,
        default=None,
        help="commits 类页面（版本发布时间/产品基线）单屏截图高度（像素），"
        "默认为视口高度一半（450），只截视口顶部；不影响其它页面",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="网页登录用户名（或环境变量 GITLABSHOT_USERNAME）；token 网页认证失败时用用户名+密码表单登录",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="网页登录密码（或环境变量 GITLABSHOT_PASSWORD）；与 --username 配合",
    )

    args = parser.parse_args()

    # 0. 解析 --only：只截指定内置类型（master/baseline/release/tag）
    #    支持逗号分隔或多次传入；不传则全截（不过滤）
    valid_types = {"master", "baseline", "release", "tag"}
    only_types: set = set()
    if args.only:
        for part in args.only:
            for name in part.split(","):
                name = name.strip().lower()
                if name:
                    only_types.add(name)
        unknown = only_types - valid_types
        if unknown:
            print(
                f"错误：--only 含未知类型：{', '.join(sorted(unknown))}"
                f"（可选：{', '.join(sorted(valid_types))}）"
            )
            return 1

    # 1. 加载配置文件（若指定），命令行参数优先
    from gitlabshot.config_loader import load_config_file, ConfigFileError

    cfg_file: dict = {}
    if args.config:
        try:
            cfg_file = load_config_file(args.config)
        except ConfigFileError as exc:
            print(f"错误：{exc}")
            return 1

    # 2. 解析必填项：project_url 与 token（命令行 > 配置文件 > 环境变量）
    project_url = args.project_url or cfg_file.get("project_url")
    token = (
        args.token
        or cfg_file.get("token")
        or os.environ.get("GITLABSHOT_TOKEN")
    )
    if not project_url or not token:
        print("错误：缺少 project_url 或 token（可通过命令行、配置文件或环境变量提供）")
        parser.print_help()
        return 1

    # 网页登录回退凭证（可选）：命令行 > 配置文件 > 环境变量
    username_arg = (
        args.username or cfg_file.get("username") or os.environ.get("GITLABSHOT_USERNAME")
    )
    password_arg = (
        args.password or cfg_file.get("password") or os.environ.get("GITLABSHOT_PASSWORD")
    )
    executable_arg = args.executable_path or cfg_file.get("executable_path")
    baseline_tag_val = args.baseline_tag or cfg_file.get("baseline_tag") or "20250901_Release"
    release_tag_val = args.release_tag or cfg_file.get("release_tag")
    output_dir_val = args.output_dir if args.output_dir != "." else cfg_file.get("output_dir", ".")
    pkg_name_val = args.pkg_name or cfg_file.get("pkg_name")

    # 3. 解析视口 WxH（配置文件可覆盖默认值）
    viewport_str = cfg_file.get("viewport", args.viewport)
    try:
        w_str, h_str = str(viewport_str).split("x")
        viewport_width = int(w_str)
        viewport_height = int(h_str)
    except (ValueError, AttributeError):
        print(f"错误：视口格式无效：{viewport_str}（应为 WxH，如 1440x900）")
        return 1

    # 4. 构建 Config
    config = Config(
        project_url=project_url,
        token=token,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        wait_ms=cfg_file.get("wait", args.wait),
        max_screens=cfg_file.get("max_screens", args.max_screens),
        keep_fixed=cfg_file.get("keep_fixed", args.keep_fixed),
        output_dir=output_dir_val,
        pkg_name=pkg_name_val,
        branches=args.branch or [],
        executable_path=executable_arg,
        baseline_tag=baseline_tag_val,
        release_tag=release_tag_val,
        commit_max_screens=args.commit_screens,
        commit_viewport_height=(
            args.commit_viewport_height
            if args.commit_viewport_height is not None
            else cfg_file.get("commit_viewport_height", 450)
        ),
        username=username_arg,
        password=password_arg,
    )

    # 4b. 解析项目地址并填入 config
    try:
        base_url, project_path, url_encoded_path = parse_project_url(config.project_url)
    except Exception as exc:
        print(f"错误：项目地址解析失败：{exc}")
        return 1
    config.base_url = base_url
    config.project_path = project_path
    config.url_encoded_path = url_encoded_path

    print(
        f"目标项目：{config.project_path}（{config.base_url}）"
        f" token={config.mask_token()}"
    )

    # 5. 创建 API 客户端并验证 token
    client = GitLabAPIClient(config.base_url, config.token, config.verify_ssl)
    try:
        username = client.verify_token()
    except InvalidTokenError:
        print("错误：Token 无效或无权限")
        return 5
    print(f"Token 验证通过，用户：{username}")

    # 6. 获取项目元数据
    try:
        project = client.get_project(config.url_encoded_path)
    except APIError as exc:
        print(f"错误：获取项目失败（{exc}）")
        return 2
    project_id = project["id"]
    default_branch = project["default_branch"]
    print(f"项目 ID：{project_id}，默认分支：{default_branch}")

    # 7. 启动浏览器（网页会话改用用户名+密码表单登录）
    try:
        browser, context, page = launch_browser(config)
    except ChromiumMissingError as exc:
        print(f"错误：Chromium 不可用（{exc}）")
        return 4

    # 网页登录需要用户名+密码（token 方式的网页认证已确认不可用）
    if not (config.username and config.password):
        print(
            "错误：网页登录需要用户名与密码（token 仅用于 API）。"
            "请通过 --username/--password 或环境变量 "
            "GITLABSHOT_USERNAME/GITLABSHOT_PASSWORD 或配置文件提供。"
        )
        return 1

    tmp_dir = None
    try:
        # 8. 建立网页会话：用户名+密码表单登录
        try:
            establish_session_form(
                page, config.base_url, config.username, config.password, "password"
            )
            print("GitLab 网页登录成功（用户名+密码表单登录）")
        except LoginError as exc:
            print(f"错误：GitLab 网页登录失败（{exc}）")
            return 5

        # 9. 准备输出目录与包名
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        pkg_name = config.pkg_name or config.project_path.rstrip("/").split("/")[-1]
        print(f"输出目录：{output_dir}，包名前缀：{pkg_name}")
        total_saved = 0

        # 临时目录（capture_page 中间产物，save_images 会移动走）
        tmp_dir = Path(tempfile.mkdtemp(prefix="gitlabshot_"))

        # 10. 主线截图（master 分支，仓库根 URL，整页滚动）
        if only_types and "master" not in only_types:
            print("跳过主线截图（--only 未包含 master）")
        else:
            print(f"正在截图主线 {default_branch}...")
            master_url = f"{config.base_url}/{config.project_path}"
            try:
                master_imgs = capture_page(
                    page, master_url, config, tmp_dir, target_x=48,
                )
            except NavigationError as exc:
                print(f"警告：{exc}，已跳过")
                master_imgs = []
            total_saved += len(save_images(master_imgs, output_dir, pkg_name, "master"))

        # 11. 送测产品基线版本截图
        # 取 baseline_tag 的 commit A，再取 A 之后（newer）第 2 个 commit C，
        # 用 C 打开 /-/commits/C，页面显示 C、中间 commit、A 前3个提交
        if only_types and "baseline" not in only_types:
            print("跳过产品基线截图（--only 未包含 baseline）")
        else:
            baseline_target_sha = None
            baseline_label = ""
            try:
                baseline_target_sha = client.get_tag_commit(project_id, config.baseline_tag)
                baseline_label = config.baseline_tag
                baseline_mode = "tag"
            except TagNotFoundError:
                baseline_mode = "root"
                print(f"提示：未找到基线标签 {config.baseline_tag}，改用初始提交")
            except APIError as exc:
                print(f"警告：获取基线标签失败（{exc}），跳过产品基线")
                baseline_mode = None

            if baseline_mode:
                try:
                    commits = client.list_commits(project_id, default_branch)
                except APIError as exc:
                    print(f"警告：获取提交历史失败（{exc}），跳过产品基线")
                    commits = []

                if commits:
                    if baseline_mode == "root":
                        try:
                            baseline_target_sha = client.get_root_commit(
                                project_id, default_branch
                            )
                            baseline_label = "初始提交"
                        except APIError as exc:
                            print(f"警告：获取初始提交失败（{exc}），跳过产品基线")
                            baseline_target_sha = None

                    if baseline_target_sha:
                        # 取 target 之后（newer，时间更晚）的 2 个 commit
                        context_shas = client.find_commit_context(
                            commits, baseline_target_sha, "newer", count=2,
                        )
                        if context_shas:
                            # 用第 2 个（较新、最远离 target）打开 commits 页
                            open_sha = context_shas[-1]
                            print(f"正在截图产品基线 commits/{open_sha[:8]}...")
                            url = (
                                f"{config.base_url}/{config.project_path}/-/commits/"
                                f"{open_sha}"
                            )
                            try:
                                imgs = capture_page(
                                    page, url, config, tmp_dir,
                                    max_screens=config.commit_max_screens,
                                    inject_urlbar=False,
                                    shot_height=config.commit_viewport_height,
                                )
                            except NavigationError as exc:
                                print(f"警告：{exc}，已跳过")
                                imgs = []
                            total_saved += len(
                                save_images(imgs, output_dir, pkg_name, "baseline")
                            )
                        else:
                            print(f"警告：无法获取 {baseline_label} 之后的 commit，跳过产品基线")

        # 12. 送测产品版本发布时间截图（只截配置的 release_tag）
        if only_types and "release" not in only_types:
            print("跳过版本发布时间截图（--only 未包含 release）")
        elif config.release_tag:
            print(f"正在截图版本发布时间 {config.release_tag}...")
            url = (
                f"{config.base_url}/{config.project_path}/-/commits/"
                f"{urllib.parse.quote(config.release_tag, safe='')}"
            )
            try:
                imgs = capture_page(
                    page, url, config, tmp_dir,
                    max_screens=config.commit_max_screens,
                    inject_urlbar=False,
                    shot_height=config.commit_viewport_height,
                )
            except NavigationError as exc:
                print(f"警告：{exc}，已跳过")
                imgs = []
            total_saved += len(save_images(imgs, output_dir, pkg_name, "release"))
        else:
            print("提示：未配置 release_tag，跳过版本发布时间截图")

        # 13. 送测产品版本标签截图（/-/tags，截第一页）
        if only_types and "tag" not in only_types:
            print("跳过版本标签截图（--only 未包含 tag）")
        else:
            tags_list_url = f"{config.base_url}/{config.project_path}/-/tags"
            print("正在截图版本标签列表...")
            try:
                tags_imgs = capture_page(
                    page, tags_list_url, config, tmp_dir, inject_urlbar=False,
                )
            except NavigationError as exc:
                print(f"警告：{exc}，已跳过")
                tags_imgs = []
            total_saved += len(save_images(tags_imgs, output_dir, pkg_name, "tag"))

        # 14. 分支截图（排除 master 的其它分支）
        #     --only 指定后分支不属于内置 4 类，整段跳过
        if only_types:
            print("跳过分支截图（已指定 --only）")
        else:
            if config.branches:
                branches = config.branches
            else:
                try:
                    branches = client.list_branches(project_id)
                except APIError as exc:
                    print(f"警告：API 调用失败（{exc}），跳过对应内容")
                    branches = []
            # 排除 master（已在主线截取）
            other_branches = [b for b in branches if b != default_branch]
            for branch in other_branches:
                print(f"正在截图分支 {branch}...")
                url = (
                    f"{config.base_url}/{config.project_path}/-/tree/"
                    f"{urllib.parse.quote(branch, safe='')}"
                )
                try:
                    imgs = capture_page(page, url, config, tmp_dir)
                except NavigationError as exc:
                    print(f"警告：{exc}，已跳过")
                    continue
                total_saved += len(save_images(imgs, output_dir, pkg_name, branch))

        # 15. 关闭浏览器
        try:
            browser.close()
        except Exception:
            pass

        # 16. 检查是否有截图
        if total_saved == 0:
            print("错误：未捕获到任何截图")
            return 3

        # 17. 成功
        print(f"完成，共保存 {total_saved} 张截图到 {output_dir}")
        return 0
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            browser.close()
        except Exception:
            pass


if __name__ == "__main__":
    import sys

    sys.exit(main())

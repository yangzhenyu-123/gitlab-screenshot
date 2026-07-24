"""GitLab 仓库审计截图工具 CLI 入口与主编排模块。

串联 config / gitlab_api / gitlab_auth / capture / preprocess / docx_writer
各模块，按「分支文件树 → Tags 列表 → Tag Commits → Context」顺序逐屏截图，
并生成含审计截图的 Word 文档。

退出码：
    0  成功
    1  参数错误（缺 URL/token）
    2  导航失败/项目不可达/文档生成失败
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
from gitlabshot.gitlab_auth import (
    LoginError,
    establish_session_basic,
    establish_session_form,
    verify_session,
)
from gitlabshot.capture import (
    ChromiumMissingError,
    NavigationError,
    capture_page,
    launch_browser,
)
from gitlabshot.docx_writer import (
    Chapter,
    DocContent,
    SubSection,
    build_docx,
)


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
        description="GitLab 仓库审计逐屏截图转 Word 工具",
    )
    parser.add_argument("project_url", nargs="?", help="GitLab 项目地址")
    parser.add_argument(
        "--token",
        default=None,
        help="Personal Access Token（或环境变量 GITLABSHOT_TOKEN）",
    )
    parser.add_argument(
        "-o", "--output", default="audit.docx", help="输出 docx 路径"
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
        "--continuous", action="store_true", help="连续排列（不分页）"
    )
    parser.add_argument(
        "--format", choices=["png", "jpeg"], default="png", help="图片格式"
    )
    parser.add_argument("--quality", type=int, default=85, help="JPEG 质量")
    parser.add_argument("--margin", type=float, default=0.5, help="页边距（英寸）")
    parser.add_argument("--dpi", type=int, default=96, help="DPI")
    parser.add_argument(
        "--branch", action="append", default=None, help="指定分支（可多次）"
    )
    parser.add_argument(
        "--context-tag", default=None, help="指定 tag 做上下文截图"
    )
    parser.add_argument(
        "--context-direction",
        choices=["newer", "older"],
        default="newer",
        help="上下文方向",
    )
    parser.add_argument(
        "--executable-path", default=None, help="指定 Chromium 路径"
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

    # 1. 校验必填：project_url 与 token（参数 + 环境变量）
    token = args.token or os.environ.get("GITLABSHOT_TOKEN")
    if not args.project_url or not token:
        parser.print_help()
        return 1

    # 网页登录回退凭证（可选）
    username_arg = args.username or os.environ.get("GITLABSHOT_USERNAME")
    password_arg = args.password or os.environ.get("GITLABSHOT_PASSWORD")

    # 2. 解析视口 WxH
    try:
        w_str, h_str = args.viewport.split("x")
        viewport_width = int(w_str)
        viewport_height = int(h_str)
    except (ValueError, AttributeError):
        print(f"错误：视口格式无效：{args.viewport}（应为 WxH，如 1440x900）")
        return 1

    # 3. 构建 Config
    config = Config(
        project_url=args.project_url,
        token=token,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        wait_ms=args.wait,
        max_screens=args.max_screens,
        keep_fixed=args.keep_fixed,
        image_format=args.format,
        quality=args.quality,
        dpi=args.dpi,
        output_path=args.output,
        continuous=args.continuous,
        margin_inches=args.margin,
        branches=args.branch or [],
        context_tag=args.context_tag,
        context_direction=args.context_direction,
        executable_path=args.executable_path,
        username=username_arg,
        password=password_arg,
    )

    # 4. 解析项目地址并填入 config
    try:
        base_url, project_path, url_encoded_path = parse_project_url(args.project_url)
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

    # 7. 启动浏览器（带 HTTP Basic Auth 凭证，避免表单登录）
    #     GitLab 支持 oauth2 + PAT 通过 Basic Auth 访问受保护页面
    from urllib.parse import urlsplit as _urlsplit

    _base_parts = _urlsplit(config.base_url)
    _origin = f"{_base_parts.scheme}://{_base_parts.netloc}"
    _http_credentials = {
        "username": "oauth2",
        "password": config.token,
        "origin": _origin,
    }
    try:
        browser, context, page = launch_browser(config, _http_credentials)
    except ChromiumMissingError as exc:
        print(f"错误：Chromium 不可用（{exc}）")
        return 4

    tmp_dir = None
    try:
        # 8. 建立网页会话：优先 private_token URL 认证（最可靠），
        #    Basic Auth 凭证已在创建 context 时注入，
        #    均失败则回退表单登录
        session_ok = False
        try:
            establish_session_basic(context, config.base_url, config.token)
            if verify_session(
                page, config.base_url, config.project_path, config.token
            ):
                session_ok = True
                print("GitLab 网页会话建立成功（private_token / Basic Auth）")
        except Exception as exc:
            print(f"警告：private_token / Basic Auth 方式失败（{exc}），尝试表单登录回退")

        if not session_ok:
            # token 网页认证失败：优先用提供的用户名+密码表单登录
            login_user = config.username or username  # 显式用户名优先，否则用 API 获取的
            login_pass = config.password if (config.username and config.password) else config.token
            try:
                establish_session_form(
                    page, config.base_url, login_user, login_pass
                )
                print("GitLab 网页登录成功（表单登录）")
            except LoginError as exc:
                print(f"错误：GitLab 网页登录失败（{exc}）")
                return 5

        # 9. 创建临时目录
        tmp_dir = Path(tempfile.mkdtemp(prefix="gitlabshot_"))

        # 10. 初始化文档内容
        content = DocContent()

        # 11. 分支文件树章
        if config.branches:
            branches = config.branches
        else:
            try:
                branches = client.list_branches(project_id)
            except APIError as exc:
                print(f"警告：API 调用失败（{exc}），跳过对应内容")
                branches = []
        branch_subsections: list[SubSection] = []
        for branch in branches:
            print(f"正在截图分支 {branch}...")
            url = (
                f"{config.base_url}/{config.project_path}/tree/"
                f"{urllib.parse.quote(branch, safe='')}"
            )
            try:
                imgs = capture_page(page, url, config, tmp_dir)
            except NavigationError:
                print(f"警告：页面 {url} 截图失败，已跳过")
                continue
            if imgs:
                branch_subsections.append(SubSection(title=branch, images=imgs))
        if branch_subsections:
            content.chapters.append(
                Chapter(title="分支文件树", subsections=branch_subsections)
            )

        # 12. Tags 列表章
        tags_list_url = f"{config.base_url}/{config.project_path}/-/tags"
        print("正在截图 Tags 列表...")
        try:
            tags_imgs = capture_page(page, tags_list_url, config, tmp_dir)
        except NavigationError:
            print(f"警告：页面 {tags_list_url} 截图失败，已跳过")
            tags_imgs = []
        if tags_imgs:
            content.chapters.append(
                Chapter(
                    title="Tags 列表",
                    subsections=[SubSection(title="", images=tags_imgs)],
                )
            )

        # 13. Tag Commits 章
        try:
            tags = client.list_tags(project_id)
        except APIError as exc:
            print(f"警告：API 调用失败（{exc}），跳过对应内容")
            tags = []
        tag_commit_subsections: list[SubSection] = []
        for tag_name, commit_sha in tags:
            print(f"正在截图 Tag {tag_name} 的 commit...")
            url = f"{config.base_url}/{config.project_path}/-/commit/{commit_sha}"
            try:
                imgs = capture_page(page, url, config, tmp_dir)
            except NavigationError:
                print(f"警告：页面 {url} 截图失败，已跳过")
                continue
            if imgs:
                tag_commit_subsections.append(
                    SubSection(title=tag_name, images=imgs)
                )
        if tag_commit_subsections:
            content.chapters.append(
                Chapter(title="Tag Commits", subsections=tag_commit_subsections)
            )

        # 14. Context 章（若指定 context_tag）
        if config.context_tag:
            try:
                target_sha = client.get_tag_commit(project_id, config.context_tag)
            except TagNotFoundError:
                print(f"警告：Tag {config.context_tag} 不存在，跳过上下文截图")
                target_sha = None
            except APIError as exc:
                print(f"警告：API 调用失败（{exc}），跳过对应内容")
                target_sha = None

            if target_sha:
                try:
                    commits = client.list_commits(project_id, default_branch)
                except APIError as exc:
                    print(f"警告：API 调用失败（{exc}），跳过对应内容")
                    commits = []
                context_shas = client.find_commit_context(
                    commits,
                    target_sha,
                    config.context_direction,
                    count=2,
                )
                commit_list = [(target_sha, "target")] + [
                    (sha, f"{config.context_direction} {i + 1}")
                    for i, sha in enumerate(context_shas)
                ]
                context_subsections: list[SubSection] = []
                # 说明性 Heading 2 子节（无截图）
                context_subsections.append(
                    SubSection(
                        title=(
                            f"说明：{config.context_tag} 的 commit 及后两个 commit"
                            f"（方向：{config.context_direction}）"
                        ),
                        images=[],
                        level=2,
                    )
                )
                for sha, label in commit_list:
                    print(f"正在截图 Context {label}（{sha[:8]}）...")
                    url = f"{config.base_url}/{config.project_path}/-/commit/{sha}"
                    try:
                        imgs = capture_page(page, url, config, tmp_dir)
                    except NavigationError:
                        print(f"警告：页面 {url} 截图失败，已跳过")
                        continue
                    if imgs:
                        context_subsections.append(
                            SubSection(
                                title=f"{label} ({sha[:8]})",
                                images=imgs,
                                level=3,
                            )
                        )
                # 仅当至少有一个 commit 截图时才追加章节（说明子节无图）
                if any(sub.images for sub in context_subsections):
                    content.chapters.append(
                        Chapter(
                            title=f"Context: {config.context_tag}",
                            subsections=context_subsections,
                        )
                    )

        # 15. 关闭浏览器
        try:
            browser.close()
        except Exception:
            pass

        # 16. 检查是否有截图
        if not content.chapters:
            print("错误：未捕获到任何截图")
            return 3

        # 17. 生成文档
        try:
            build_docx(content, config.output_path, config)
        except Exception as exc:
            print(f"警告：文档生成失败（{exc}）")
            return 2

        # 18. 成功
        print(f"已生成文档：{config.output_path}")
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

# Tasks

- [x] Task 1: 搭建项目骨架与依赖声明
  - [ ] SubTask 1.1: 创建 `pyproject.toml`，声明依赖 `playwright>=1.40`、`python-docx>=1.0`、`Pillow>=10.0`、`requests>=2.28`，定义 `[project.scripts]` 入口 `gitlabshot = "gitlabshot.cli:main"`
  - [ ] SubTask 1.2: 创建 `requirements.txt`（与 pyproject 依赖一致，用于离线 `pip download`）
  - [ ] SubTask 1.3: 创建 `gitlabshot/__init__.py`（空）与 `gitlabshot/config.py`（`Config` 数据类，含所有默认值：视口、等待、最大屏数、隐藏固定、格式、连续、边距、DPI、context-direction、token、项目 URL 等）
  - [ ] SubTask 1.4: 验证 `pip install -e .` 可成功安装，`gitlabshot --help` 可执行

- [x] Task 2: 实现 GitLab API 客户端 `gitlab_api.py`
  - [ ] SubTask 2.1: 实现 `GitLabAPIClient(base_url, token, verify_ssl=False)`，所有请求携带 `PRIVATE-TOKEN` header，`requests` 关闭 SSL 验证，含重试逻辑（429/5xx 重试 3 次间隔递增）
  - [ ] SubTask 2.2: 实现 `verify_token() -> username`：调用 `GET /user`，401 抛 `InvalidTokenError`
  - [ ] SubTask 2.3: 实现 `get_project(url_encoded_path) -> dict`：调用 `GET /projects/{path}`，返回 `id`、`default_branch`
  - [ ] SubTask 2.4: 实现 `list_branches(project_id) -> list[str]`：翻页调用 `GET /projects/{id}/repository/branches?per_page=100`
  - [ ] SubTask 2.5: 实现 `list_tags(project_id) -> list[(name, commit_sha)]`：翻页调用 `GET /projects/{id}/repository/tags?per_page=100`，返回 `(tag_name, commit.id)`
  - [ ] SubTask 2.6: 实现 `get_tag_commit(project_id, tag_name) -> sha`：调用 `GET /projects/{id}/repository/tags/{tag_name}`，404 抛 `TagNotFoundError`
  - [ ] SubTask 2.7: 实现 `list_commits(project_id, ref_name) -> list[(sha, short_id, date)]`：翻页调用 `GET /projects/{id}/repository/commits?ref_name={ref}&per_page=100`
  - [ ] SubTask 2.8: 实现 `find_commit_context(commits, target_sha, direction, count=2) -> list[sha]`：在 commit 列表中定位 target_sha，按方向取相邻 count 个 commit SHA

- [x] Task 3: 实现 GitLab 网页认证模块 `gitlab_auth.py`
  - [ ] SubTask 3.1: 实现 `establish_session(page, base_url, username, token)`：访问 `{base_url}/users/sign_in`，等待 `#user_login` 与 `#user_password`，填充 username 与 token（作为密码），点击提交，等待跳转
  - [ ] SubTask 3.2: 实现登录校验：URL 不含 `/users/sign_in` 即视为成功，失败抛 `LoginError`
  - [ ] SubTask 3.3: 实现日志脱敏：token 仅显示前 4 位 + `***`

- [x] Task 4: 实现逐视口截图核心模块 `capture.py`
  - [ ] SubTask 4.1: 实现 `launch_browser(config)`：Chromium 启动参数含 `--disable-blink-features=AutomationControlled`、`--no-sandbox`、`--disable-dev-shm-usage`，支持 `executable_path`，上下文 `ignore_https_errors=True`，注入 `navigator.webdriver` 隐藏脚本与 UA，设置视口
  - [ ] SubTask 4.2: 实现 `capture_page(page, url, config) -> list[Path]`：`page.goto(url, wait_until="networkidle")`，捕获超时/连接错误抛 `NavigationError`
  - [ ] SubTask 4.3: 实现固定元素隐藏 CSS 注入（GitLab 选择器：`.navbar-gitlab`、`.top-bar`、`.nav-sidebar`、`.sidebar-container`、`.layout-wrapper .nav-wrapper`，调整 `.content-wrapper` margin/padding 为 0），除非 `config.keep_fixed`
  - [ ] SubTask 4.4: 实现懒加载处理：移除 `img` 的 `loading` 属性，预滚动步进到底部 + 等待，等待 `networkidle`，回滚顶部，重新读 `scrollHeight`
  - [ ] SubTask 4.5: 实现主截图循环：按视口高度逐步滚动，每步 `wait_for_timeout(config.wait_ms)`，`full_page=False` 截图，存临时目录，受 `config.max_screens` 兜底；处理整除与最后一屏不足视口

- [x] Task 5: 实现图像预处理模块 `preprocess.py`
  - [ ] SubTask 5.1: 实现 `preprocess_image(path, config) -> Path`：PIL 打开，按 `config.image_format` 与 `config.quality` 重新保存，写入 `config.dpi` 元数据
  - [ ] SubTask 5.2: PNG 忽略 quality，JPEG 应用 quality
  - [ ] SubTask 5.3: 验证处理后 `img.info["dpi"]` 正确

- [x] Task 6: 实现 Word 文档生成模块 `docx_writer.py`
  - [ ] SubTask 6.1: 定义数据结构 `Chapter`（含 `title`、`level`、`subsections: list[(subtitle, list[Path])]`）与 `DocContent`（含 `chapters: list[Chapter]`）
  - [ ] SubTask 6.2: 实现 `build_docx(content: DocContent, output_path, config)`：设置所有 section 边距为 `config.margin_inches`，计算页面可用宽度
  - [ ] SubTask 6.3: 遍历章节：插入 Heading 1（章标题）→ 遍历子节：插入 Heading 2（子标题）→ 遍历截图：`preprocess_image` 后 `add_picture(width=可用宽度)`，按 `config.continuous` 决定是否 `add_page_break`
  - [ ] SubTask 6.4: 支持 Heading 3（用于 context 章节标注每个 commit），按层级插入
  - [ ] SubTask 6.5: 章节之间插入分页符；空章节跳过
  - [ ] SubTask 6.6: 保存到 `output_path`

- [x] Task 7: 实现 CLI 入口与编排 `cli.py`
  - [ ] SubTask 7.1: 用 argparse 定义参数：`project_url`、`--token`（必填，或环境变量 `GITLABSHOT_TOKEN`）、`-o/--output`、`--viewport`（WxH）、`--wait`、`--max-screens`、`--keep-fixed`、`--continuous`、`--format`、`--quality`、`--margin`、`--dpi`、`--branch`（action append）、`--context-tag`、`--context-direction`（newer/older，默认 newer）、`--executable-path`
  - [ ] SubTask 7.2: 支持环境变量 `GITLABSHOT_TOKEN`、`PLAYWRIGHT_BROWSERS_PATH`
  - [ ] SubTask 7.3: 实现主编排：解析参数 → 构建 Config → 解析项目 URL（base_url + url_encoded_path）→ `GitLabAPIClient` 验证 token 获取 username → `get_project` 获取 id + default_branch → 启动浏览器 → `establish_session` 登录 → 按章节截图：
    - 分支文件树章节：`list_branches`（或用 `--branch`）→ 对每个分支 `capture_page(tree_url)`
    - Tags 列表章节：`capture_page(tags_url)`
    - Tag Commits 章节：`list_tags` → 对每个 tag `capture_page(commit_url)`
    - （若 `--context-tag`）Context 章节：`get_tag_commit` + `list_commits(default_branch)` + `find_commit_context` → 对每个 sha `capture_page(commit_url)`
  - [ ] SubTask 7.4: 收集所有截图到 `DocContent`，调用 `build_docx`，清理临时目录
  - [ ] SubTask 7.5: 定义异常 `InvalidTokenError`、`LoginError`、`NavigationError`、`ChromiumMissingError`、`TagNotFoundError`；在主流程捕获并返回退出码（1 参数错误、2 导航失败、3 无截图、4 Chromium 缺失、5 token/登录失败）
  - [ ] SubTask 7.6: API 失败时跳过对应章节并警告；指定 tag 不存在时跳过 context 章节并警告；全部章节为空时以退出码 3 退出

- [ ] Task 8: 集成验证
  - [ ] SubTask 8.1: 端到端冒烟：对内网 GitLab 项目 `gitlabshot <url> --token <PAT> --branch <branch> -o out.docx`，确认生成 docx 含「分支文件树」「Tags 列表」「Tag Commits」三个 Heading 1 章节与非空截图
  - [ ] SubTask 8.2: 验证 `--context-tag <tag>` 生成 context 章节，含 3 个 commit 详情页截图与 Heading 3 标注
  - [ ] SubTask 8.3: 验证 `--context-direction older` 取更旧的两个 commit
  - [ ] SubTask 8.4: 验证 `--continuous`、`--keep-fixed`、`--max-screens`、`--branch` 参数行为符合 spec
  - [ ] SubTask 8.5: 验证 token 无效时退出码 5，token 日志脱敏
  - [ ] SubTask 8.6: 验证 `--executable-path` 指定系统 Chromium 可正常工作
  - [ ] SubTask 8.7: 验证自签名证书场景不被阻断（`ignore_https_errors` + `verify=False`）

- [x] Task 9: 修复静态验证发现的 spec 偏差
  - [x] SubTask 9.1: 修复 Context 章节层级结构。`docx_writer.py` 的 `SubSection` 增加 `level: int = 2` 字段，`build_docx` 中使用 `doc.add_heading(subsection.title, level=subsection.level)`；`cli.py` Context 章节新增一个说明性 SubSection（level=2，title 为说明文本，images 为空）作为首子节，各 commit SubSection 改为 level=3；更新 `Chapter` 数据类 docstring。章节空跳过逻辑改为 `if not any(sub.images for sub in chapter.subsections): continue`（说明性子节无图不影响判断）。
  - [x] SubTask 9.2: 修复 `--continuous` 子节间分页。`build_docx` 在 subsection 循环中，当 `config.continuous` 且非章内首个子节时，插入 `doc.add_page_break()`，实现"同 Heading 2 内截图不分页，但章节/子节间仍分页"。同时跳过无标题且无图片的空子节。

# Task Dependencies
- Task 2、Task 3、Task 5 可在 Task 1 完成后并行开发
- Task 4 依赖 Task 1
- Task 6 依赖 Task 1、Task 5
- Task 7 依赖 Task 1~Task 6 全部完成
- Task 8 依赖 Task 1~Task 7 全部完成
- Task 9 依赖 Task 8 静态验证

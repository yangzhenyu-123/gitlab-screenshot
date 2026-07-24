# Checklist

## 项目骨架与依赖
- [x] `pyproject.toml` 声明 `playwright`、`python-docx`、`Pillow`、`requests` 依赖，定义 `gitlabshot` 命令入口
- [x] `requirements.txt` 存在，用于离线 `pip download`
- [x] `gitlabshot/config.py` 存在 `Config` 数据类，含视口、等待、最大屏数、隐藏固定、格式、连续、边距、DPI、context-direction、token、项目 URL 等字段及默认值
- [ ] `gitlabshot --help` 可正常执行

## CLI 接口
- [x] `cli.py` 使用 argparse 定义所有 spec 列出的参数
- [x] `--token` 必填（或环境变量 `GITLABSHOT_TOKEN`），缺失时退出码 1
- [x] 缺少项目地址时以退出码 1 退出并打印用法
- [x] 支持 `--branch` 多次指定（action append）
- [x] 支持 `--context-tag` 与 `--context-direction newer|older`
- [x] 支持 `--executable-path` 指定系统 Chromium 路径
- [x] 支持环境变量 `GITLABSHOT_TOKEN`、`PLAYWRIGHT_BROWSERS_PATH`

## GitLab API 客户端
- [x] `gitlab_api.py` 所有请求携带 `PRIVATE-TOKEN` header，默认 `verify=False`
- [x] `verify_token()` 调用 `GET /user`，401 抛 `InvalidTokenError`，成功返回 username
- [x] `get_project()` 调用 `GET /projects/{url_encoded_path}`，返回 id 与 default_branch
- [x] `list_branches()` 翻页获取全部分支名
- [x] `list_tags()` 翻页获取所有 `(tag_name, commit_sha)`
- [x] `get_tag_commit()` 调用 `GET /repository/tags/{name}`，404 抛 `TagNotFoundError`
- [x] `list_commits(ref_name)` 翻页获取 commit 历史
- [x] `find_commit_context()` 能在 commit 列表定位 target_sha 并按方向取相邻 2 个
- [x] 429/5xx 重试 3 次间隔递增，仍失败跳过对应内容并警告

## GitLab 网页认证
- [x] `establish_session()` 访问 `/users/sign_in`，填充 `#user_login`（username）与 `#user_password`（token），点击提交
- [x] 登录后 URL 不含 `/users/sign_in` 视为成功，失败抛 `LoginError`
- [x] token 在日志中仅显示前 4 位 + `***`
- [x] 公开项目仍要求 token（统一认证流程）

## 浏览器与截图核心
- [x] Chromium 启动参数含 `--disable-blink-features=AutomationControlled`、`--no-sandbox`、`--disable-dev-shm-usage`
- [x] 上下文注入 `navigator.webdriver` 隐藏脚本与常见 User-Agent
- [x] 上下文默认 `ignore_https_errors=True`
- [x] 支持 `--executable-path` 启动指定 Chromium
- [x] 截图前移除所有 `img` 的 `loading` 属性
- [x] 截图前执行预滚动触发懒加载，等待 `networkidle`，回滚顶部
- [x] 预滚动后重新读取 `scrollHeight` 作为最终总高度
- [x] 默认注入 CSS 隐藏 `.navbar-gitlab`、`.top-bar`、`.nav-sidebar`、`.sidebar-container`，并调整 `.content-wrapper` margin/padding 为 0
- [x] `--keep-fixed` 时不注入隐藏 CSS
- [x] 主截图循环使用 `full_page=False`，按视口高度逐步滚动
- [x] 页面高度整除视口时不产生多余空白屏
- [x] 最后一屏不足视口时按实际可见内容截取
- [x] 超长页面受 `--max-screens` 兜底，达到上限打印警告

## 图像预处理
- [x] `preprocess.py` 对截图重新保存并写入 DPI 元数据（默认 96）
- [x] PNG 忽略 quality，JPEG 应用 quality

## Word 文档生成
- [x] `docx_writer.py` 设置文档边距为配置值（默认 0.5 英寸）
- [x] 图片宽度按页面可用宽度等比缩放插入
- [x] 文档含 4 类 Heading 1 章节：分支文件树 / Tags 列表 / Tag Commits / Context（可选）
- [x] 分支文件树章节：每个分支 Heading 2 + 截图
- [x] Tag Commits 章节：每个 tag Heading 2 + commit 详情页截图
- [x] Context 章节：Heading 2 说明 + 每个 commit Heading 3（含 short SHA 与方向标记）+ 截图
- [x] 默认每张截图后分页；`--continuous` 时同 Heading 2 内截图不分页，但章节/子节间仍分页
- [x] 空章节跳过，不插入空标题

## 错误处理与退出码
- [x] Token 无效（API 401）：退出码 5
- [x] 网页登录失败：退出码 5
- [x] 项目地址不可达：退出码 2
- [x] API 持续失败：跳过对应章节并警告
- [x] 指定 `--context-tag` 不存在：跳过 context 章节并警告
- [x] Chromium 缺失：退出码 4，提示安装命令
- [x] 全部章节为空：退出码 3
- [x] 参数缺失：退出码 1

## 内网部署
- [x] `requirements.txt` 可通过 `pip download` 离线打包安装
- [x] 支持 `PLAYWRIGHT_BROWSERS_PATH` 环境变量指向预下载 Chromium 目录
- [x] 支持 `--executable-path` 指定系统 Chromium
- [x] 自签名证书场景不被阻断（`ignore_https_errors=True` + API `verify=False`）

## 集成验证
- [ ] 冒烟测试：`gitlabshot <url> --token <PAT> --branch <branch> -o out.docx` 生成含 3 个 Heading 1 章节与非空截图的 docx
- [ ] `--context-tag <tag>` 生成 context 章节含 3 个 commit 截图与 Heading 3 标注
- [ ] `--context-direction older` 取更旧的两个 commit
- [ ] `--continuous`、`--keep-fixed`、`--max-screens`、`--branch` 参数行为符合 spec
- [ ] token 无效时退出码 5，日志脱敏
- [ ] `--executable-path` 指定系统 Chromium 可正常工作

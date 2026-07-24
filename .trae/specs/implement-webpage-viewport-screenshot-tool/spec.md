# GitLab 仓库审计逐屏截图转 Word 工具 Spec

## Why
在内网 GitLab 环境下，团队需要对代码仓库进行审计/统计归档：查看每个分支的文件结构、标签列表、每个标签对应的 commit，以及指定标签前后的 commit 变化。现有"全页面长截图"方案在粘贴到 Word 时需缩放、阅读体验差，且 GitLab 页面含固定顶部导航与左侧栏，长截图会重复出现这些元素。本工具**专用于 GitLab 仓库审计**，基于 Personal Access Token 认证，通过 GitLab API 定位分支/标签/commit，再用 Playwright 逐视口截图相关页面，按"分支/标签/commit 上下文"分章节合并到 Word 文档，便于内网环境下的仓库审计与归档。

## 假设与范围说明
- **运行环境**：内网，可能无外网访问，所有依赖需可离线安装（见"开发环境与工具链"章节）
- **目标系统**：GitLab 网页界面（Community Edition / Enterprise Edition 均适用）
- **认证**：用户提供 **Personal Access Token**（PAT）。工具用 token 调用 `/api/v4/user` 获取用户名，再用「用户名 + token 作为密码」通过 GitLab 登录表单建立网页会话（GitLab 官方支持 PAT 作为密码登录网页）。Token 也可直接作为 `PRIVATE-TOKEN` header 用于所有 API 调用。
- **项目范围**：单仓库一次运行（传入一个 GitLab 项目地址）。多仓库可通过脚本循环调用实现，不在工具内做批量合并。
- **"后两个 commit" 方向假设**：指 commit 历史中比该 tag commit **更新（时间上之后）** 的两个 commit，即"tag 之后发生了什么"。提供 `--context-direction newer|older` 可切换方向。
- **分支范围假设**：默认截图**所有分支**的文件树；分支过多时可通过 `--branch` 限定指定分支子集。

## What Changes
- 新增命令行工具 `gitlabshot`，输入 GitLab 项目地址 + Token → 输出 `.docx`
- Token 认证：API 验证 token + 获取用户名 → 表单登录建立会话；API 调用统一带 `PRIVATE-TOKEN` header
- 通过 GitLab API 获取：项目默认分支、所有分支列表、所有 tag 列表、tag→commit SHA 映射、commit 历史列表
- 截图内容（按章节组织到 Word）：
  1. **分支文件树**：对每个分支截图 `/{project}/tree/{branch}` 页面（逐视口滚动截完整个文件列表）
  2. **Tags 列表**：截图 `/{project}/-/tags` 页面
  3. **每个 Tag 的 commit**：对每个 tag 截图其 commit 详情页 `/{project}/-/commit/{sha}`
  4. **指定 Tag 的 commit 上下文**：用户通过 `--context-tag <tag>` 指定一个 tag，工具定位其 commit 及后两个 commit（共 3 个 commit 详情页）单独成章
- 使用 Playwright（Python 同步 API）驱动无头 Chromium，按视口高度逐屏滚动截图（`full_page=False`）
- 截图前预滚动触发懒加载，移除 `loading="lazy"`
- CSS 注入隐藏 GitLab 固定元素（`.navbar-gitlab`、`.top-bar`、`.nav-sidebar`、`.sidebar-container`），调整 `.content-wrapper` margin 为 0
- 对超长页面（如大仓库文件树、长 commits 列表）设置最大屏数保护
- 使用 python-docx 生成 Word，按"分支/标签/commit 上下文"分章节，每张截图独占一页
- 使用 PIL 对截图 DPI 预处理，避免 Word 自动压缩模糊
- 内网友好：依赖支持离线安装，Chromium 可离线部署，默认忽略自签名证书错误

## 开发环境与工具链（内网）

### 必需工具
| 工具 | 版本要求 | 用途 | 内网安装方式 |
|------|---------|------|-------------|
| Python | ≥ 3.9 | 运行环境 | 系统包管理器或离线安装包 |
| pip | 随 Python | 包管理 | 配置内网 PyPI 镜像或离线 whl |
| Playwright (Python) | ≥ 1.40 | 浏览器自动化 | `pip install playwright`（离线 whl） |
| Chromium 浏览器 | 由 Playwright 管理 | 无头渲染 | 见下方"Chromium 离线安装" |
| python-docx | ≥ 1.0 | Word 文档生成 | `pip install python-docx`（离线 whl） |
| Pillow | ≥ 10.0 | 图像 DPI 预处理 | `pip install Pillow`（离线 whl） |
| requests（或用 urllib） | ≥ 2.28 | 调用 GitLab API | `pip install requests`（离线 whl） |

### Chromium 离线安装方案（三选一）
1. **外网预下载 + 内网拷贝**：在外网机器执行 `playwright install chromium`，将 `~/.cache/ms-playwright/` 整个目录打包拷贝到内网机器同路径（或设置 `PLAYWRIGHT_BROWSERS_PATH` 环境变量指向拷贝位置）
2. **内网 HTTP 镜像**：设置环境变量 `PLAYWRIGHT_DOWNLOAD_HOST=http://内网镜像地址` 后执行 `playwright install chromium`
3. **系统 Chromium + 手动指定**：使用内网已装的系统 Chromium，通过 `--executable-path` 指定路径（需版本兼容）

### pip 依赖离线安装
- 方式 A（推荐）：在外网机器 `pip download -d ./wheels -r requirements.txt`，将 `./wheels` 拷入内网后 `pip install --no-index --find-links=./wheels -r requirements.txt`
- 方式 B：配置内网 PyPI 镜像（如 devpi、Nexus）后直接 `pip install`
- `requirements.txt` 内容：`playwright>=1.40`、`python-docx>=1.0`、`Pillow>=10.0`、`requests>=2.28`

## Impact
- Affected specs: 无（全新工具）
- Affected code:
  - 新增 `gitlabshot/` 包：
    - `cli.py`（入口与编排）
    - `config.py`（配置数据类）
    - `gitlab_api.py`（GitLab REST API 客户端：token 验证、项目信息、分支、tag、commit 历史）
    - `gitlab_auth.py`（网页会话建立：token→用户名→表单登录）
    - `capture.py`（Playwright 逐视口截图核心）
    - `docx_writer.py`（Word 文档生成）
    - `preprocess.py`（图像 DPI 预处理）
  - 新增 `pyproject.toml`：声明依赖，定义 `gitlabshot` 命令入口
  - 新增 `requirements.txt`：用于离线 `pip download`
  - 依赖外部资源：Chromium 浏览器（见离线安装方案）

## GitLab API 使用清单
所有 API 调用携带 header `PRIVATE-TOKEN: <token>`，base 为 `{base_url}/api/v4`。

| 用途 | 方法 & 路径 | 关键返回字段 |
|------|------------|-------------|
| 验证 token + 获取用户名 | `GET /user` | `username` |
| 获取项目信息（默认分支、id） | `GET /projects/{url_encoded_path}` | `id`, `default_branch` |
| 分支列表 | `GET /projects/{id}/repository/branches?per_page=100&page=N` | `[].name` |
| Tag 列表 | `GET /projects/{id}/repository/tags?per_page=100&page=N` | `[].name`, `[].commit.id` |
| 单个 Tag（含 commit） | `GET /projects/{id}/repository/tags/{tag_name}` | `commit.id` |
| Commit 历史（按 ref） | `GET /projects/{id}/repository/commits?ref_name={branch}&per_page=100&page=N` | `[].id`, `[].short_id`, `[].committed_date` |

- `url_encoded_path`：将 `group/project`（含子组）URL 编码，如 `group%2Fsubgroup%2Fproject`
- 分页：循环翻页直到返回空列表

## ADDED Requirements

### Requirement: 命令行接口
工具 SHALL 提供一个 `gitlabshot` 命令行入口，接受 GitLab 项目地址、Token 与输出路径。

#### Scenario: 基本用法
- **WHEN** 用户执行 `gitlabshot https://gitlab.internal/group/project --token <PAT> -o audit.docx`
- **THEN** 工具执行完整审计流程（分支文件树 + tags + tag commits + 默认无 context-tag），生成 `audit.docx`

#### Scenario: 仅指定 tag 上下文截图
- **WHEN** 用户执行 `gitlabshot <url> --token <PAT> --context-tag v1.2.0 -o out.docx`
- **THEN** 工具除默认内容外，额外截取 v1.2.0 的 commit 及后两个 commit 详情页，单独成章

#### Scenario: 限定分支
- **WHEN** 用户执行 `gitlabshot <url> --token <PAT> --branch main --branch develop -o out.docx`
- **THEN** 工具仅截图 main 与 develop 分支的文件树（不调用全部分支列表）

#### Scenario: 切换上下文方向
- **WHEN** 用户执行 `gitlabshot <url> --token <PAT> --context-tag v1.0 --context-direction older -o out.docx`
- **THEN** 工具截取 v1.0 的 commit 及其**更旧**的两个 commit（共 3 个）

#### Scenario: 缺少必要参数
- **WHEN** 用户未提供项目地址或 token
- **THEN** 以退出码 1 退出并打印用法说明

### Requirement: Token 认证与网页会话建立
工具 SHALL 仅凭 Personal Access Token 完成认证与网页会话建立。

#### Scenario: Token 验证与用户名获取
- **WHEN** 工具启动
- **THEN** 调用 `GET {base_url}/api/v4/user` 携带 `PRIVATE-TOKEN: <token>`
- **AND** 若返回 401，以退出码 5 退出并打印 `错误：Token 无效或无权限`
- **AND** 若成功，记录 `username` 用于后续登录

#### Scenario: 建立网页会话
- **WHEN** 浏览器启动后、首次访问项目页面前
- **THEN** 工具访问 `{base_url}/users/sign_in`，填充 `#user_login` 为上一步获取的 `username`，`#user_password` 为 token 值，点击提交，等待跳转
- **AND** 验证登录成功（URL 不含 `/users/sign_in`），失败则以退出码 5 退出

#### Scenario: Token 明文保护
- **WHEN** 工具打印任何日志或错误
- **THEN** token 仅显示前 4 位 + `***`，不输出完整 token

#### Scenario: 公开项目仍需 token（统一认证）
- **WHEN** 目标为公开项目
- **THEN** 仍要求提供 token（用于 API 调用与统一流程），无 token 时以退出码 1 退出

### Requirement: GitLab API 数据获取
工具 SHALL 通过 GitLab REST API 获取项目元数据（默认分支、分支列表、tag 列表、commit 历史），用于定位截图目标。

#### Scenario: 获取项目默认分支
- **WHEN** 工具开始处理
- **THEN** 调用 `GET /projects/{url_encoded_path}`，记录 `default_branch`，用于 commit 历史定位

#### Scenario: 获取所有分支
- **WHEN** 未指定 `--branch`
- **THEN** 调用 `GET /projects/{id}/repository/branches` 翻页直到空，记录所有分支名
- **AND** 若指定了 `--branch`，跳过 API 调用，直接使用指定分支列表

#### Scenario: 获取 Tag 与 commit 映射
- **WHEN** 工具进入 tags 截图阶段
- **THEN** 调用 `GET /projects/{id}/repository/tags` 翻页，记录每个 tag 的 `name` 与 `commit.id`

#### Scenario: 定位 tag commit 上下文
- **GIVEN** 用户指定 `--context-tag <tag>`
- **WHEN** 工具进入上下文截图阶段
- **THEN** 调用 `GET /projects/{id}/repository/tags/{tag}` 获取该 tag 的 `commit.id`
- **AND** 调用 `GET /projects/{id}/repository/commits?ref_name={default_branch}` 翻页，找到该 commit 在历史中的位置
- **AND** 根据 `--context-direction`（默认 `newer`）取相邻 2 个 commit 的 SHA
- **AND** 若未找到该 commit 或不足 2 个相邻 commit，打印警告并截取实际可得的 commit

#### Scenario: API 速率限制或错误
- **WHEN** API 返回 429 或 5xx
- **THEN** 重试 3 次（间隔递增），仍失败则跳过对应内容并打印警告

### Requirement: 逐视口截图捕获
工具 SHALL 使用 Playwright 无头浏览器，按视口高度逐屏滚动 GitLab 页面并截取当前可见视口（`full_page=False`）。

#### Scenario: 文件树页面
- **GIVEN** 一个分支文件树页面总高度 3200px，视口高度 900px
- **WHEN** 工具执行截图
- **THEN** 生成 4 张视口截图，分别对应 scrollY 0/900/1800/2700

#### Scenario: 最后一屏不足视口
- **GIVEN** 页面总高度 2000px，视口高度 900px
- **WHEN** 工具执行截图
- **THEN** 生成 3 张图片，第 3 张为 scrollY=1800 处视口截图（含底部自然空白）

#### Scenario: 页面高度整除视口
- **GIVEN** 页面总高度 1800px，视口高度 900px
- **WHEN** 工具执行截图
- **THEN** 生成 2 张图片，不多截空白屏

### Requirement: 懒加载内容处理
工具 SHALL 在正式截图前触发 GitLab 页面的懒加载资源（文件树、commits 列表、tag 列表均有懒加载）。

#### Scenario: 文件树懒加载
- **WHEN** 工具执行截图流程
- **THEN** 移除所有 `img` 的 `loading` 属性，执行预滚动（步进到底部 + 等待），等待 `networkidle`，回滚顶部
- **AND** 预滚动后重新读取 `scrollHeight`，最终截图中无空白占位

### Requirement: GitLab 固定元素隐藏
工具 SHALL 在截图前注入 CSS 隐藏 GitLab 顶部固定导航与左侧栏。

#### Scenario: 默认隐藏
- **WHEN** 用户未传 `--keep-fixed`
- **THEN** 注入 CSS：`.navbar-gitlab, .top-bar, .nav-sidebar, .sidebar-container, .layout-wrapper .nav-wrapper { display: none !important; }`，并设置 `.content-wrapper { margin: 0 !important; padding: 0 !important; }`
- **AND** 每屏截图均不含顶部导航与左侧栏

#### Scenario: 保留固定元素
- **WHEN** 用户传入 `--keep-fixed`
- **THEN** 不注入隐藏 CSS，保留 GitLab 原始布局

### Requirement: 无限滚动与超长页面保护
工具 SHALL 对超长页面（大仓库文件树、长 commits 列表）设置最大屏数上限。

#### Scenario: 超长文件树
- **WHEN** 用户设置 `--max-screens 20`（默认值），某分支文件树超过 20 屏
- **THEN** 工具最多截取 20 屏后停止，打印警告 `分支 <branch> 文件树达到最大屏数上限，可能存在未捕获内容`

### Requirement: Word 文档结构与章节组织
工具 SHALL 使用 python-docx 将截图按审计维度分章节插入文档。

#### Scenario: 文档结构
- **WHEN** 生成文档
- **THEN** 结构为：
  - Heading 1「分支文件树」→ 每个分支：Heading 2（分支名）→ 该分支文件树所有截图（每张独占一页）
  - Heading 1「Tags 列表」→ tags 列表页所有截图
  - Heading 1「Tag Commits」→ 每个 tag：Heading 2（tag 名）→ 其 commit 详情页截图
  - （若指定 `--context-tag`）Heading 1「Context: <tag>」→ Heading 2 说明（tag commit + 后两个 commit）→ 3 个 commit 详情页截图，每张前加 Heading 3 标注 commit short SHA 与方向标记

#### Scenario: 每页一图
- **WHEN** 默认模式
- **THEN** 每张截图后插入分页符，图片宽度为页面可用宽度，高度按宽高比自动计算

#### Scenario: 连续排列
- **WHEN** 用户传 `--continuous`
- **THEN** 同一 Heading 2 内的截图之间不插入分页符，但 Heading 1/Heading 2 之间仍分页

#### Scenario: 空章节跳过
- **WHEN** 某章节（如某分支文件树）未捕获任何截图
- **THEN** 跳过该章节并打印警告，不插入空标题

### Requirement: 图像质量与 DPI 处理
工具 SHALL 对截图进行 DPI 预处理，确保 Word 中清晰度符合屏幕截图预期。

#### Scenario: PNG 默认处理
- **GIVEN** Playwright 输出的 PNG 截图（无 DPI 元数据）
- **WHEN** 插入文档前
- **THEN** 使用 PIL 重新保存，写入 96 DPI 元数据，宽度按页面可用宽度等比缩放插入

#### Scenario: JPEG 选项
- **WHEN** 用户传 `--format jpeg --quality 85`
- **THEN** 截图以 JPEG 质量 85 保存并插入

### Requirement: 错误处理与退出码
工具 SHALL 对常见失败场景提供明确错误信息与非零退出码。

#### Scenario: Token 无效
- **WHEN** `/api/v4/user` 返回 401
- **THEN** 以退出码 5 退出，打印 `错误：Token 无效或无权限`

#### Scenario: 登录失败
- **WHEN** 表单登录后仍在 `/users/sign_in`
- **THEN** 以退出码 5 退出，打印 `错误：GitLab 网页登录失败`

#### Scenario: 项目地址不可达
- **WHEN** Playwright 导航超时或连接失败
- **THEN** 以退出码 2 退出

#### Scenario: API 请求失败
- **WHEN** GitLab API 持续返回错误（重试 3 次仍失败）
- **THEN** 跳过依赖该 API 的章节并打印警告，继续其他章节

#### Scenario: 指定 tag 不存在
- **WHEN** `--context-tag` 指定的 tag 在 API 中返回 404
- **THEN** 打印警告 `Tag <name> 不存在，跳过上下文截图`，跳过该章节

#### Scenario: Chromium 缺失
- **WHEN** 检测到未安装 Chromium
- **THEN** 以退出码 4 退出，打印 `错误：未检测到 Chromium，请执行 playwright install chromium 或设置 PLAYWRIGHT_BROWSERS_PATH`

#### Scenario: 未捕获任何截图
- **WHEN** 全部章节均为空
- **THEN** 以退出码 3 退出，打印 `错误：未捕获到任何截图`

### Requirement: 配置数据类
工具 SHALL 提供集中式 `Config` 数据类，封装所有可调参数及默认值。

#### Scenario: 默认配置
- **WHEN** 未传入覆盖参数
- **THEN** 配置为：视口 1440×900、等待 800ms、最大屏数 20、隐藏固定元素 True、格式 PNG、每页一图 True、边距 0.5 英寸、DPI 96、context-direction newer、捕获全集（分支+tags+tag commits）

#### Scenario: 参数覆盖
- **WHEN** 用户传入对应 CLI 参数或环境变量
- **THEN** 数据类对应字段被覆盖，未传入字段保持默认

### Requirement: 内网部署友好
工具 SHALL 支持在内网无外网环境下部署运行。

#### Scenario: 离线依赖安装
- **WHEN** 内网机器无外网
- **THEN** 通过 `requirements.txt` + `pip download` 离线包方式安装全部 Python 依赖
- **AND** Chromium 通过 `PLAYWRIGHT_BROWSERS_PATH` 指向预下载目录，或通过 `--executable-path` 指向系统 Chromium

#### Scenario: 自定义 Chromium 路径
- **WHEN** 用户传 `--executable-path /usr/bin/chromium-browser`
- **THEN** 工具使用该路径启动浏览器，跳过 Playwright 自带 Chromium

#### Scenario: 忽略 HTTPS 证书错误
- **WHEN** 内网 GitLab 使用自签名证书
- **THEN** 浏览器上下文默认 `ignore_https_errors=True`，且 API 请求默认 `verify=False`，避免证书错误阻断

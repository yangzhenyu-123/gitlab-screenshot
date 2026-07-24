# gitlabshot — GitLab 仓库审计逐屏截图转 Word 工具

在内网 GitLab 环境下，对代码仓库进行审计/统计归档：自动截取**每个分支的文件树**、**Tags 列表**、**每个 Tag 的 commit 详情页**，以及**指定 Tag 的 commit 上下文**，按"分支/标签/commit 上下文"分章节合并到 Word 文档。

与"全页面长截图"方案不同，本工具按**浏览器视口高度逐屏截图**（`full_page=False`），每张图高度不超过一屏，粘贴到 Word 后无需缩放、阅读体验好；同时自动隐藏 GitLab 固定顶部导航与左侧栏，避免每屏重复出现这些元素。

---

## 功能特性

- **Token 认证**：仅凭 Personal Access Token (PAT) 完成 API 调用与网页会话建立（token→用户名→表单登录）
- **逐视口截图**：Playwright 无头 Chromium 按视口高度滚动，每屏单独保存
- **懒加载处理**：截图前移除 `loading` 属性、预滚动触发加载、等待 `networkidle`
- **固定元素隐藏**：默认注入 CSS 隐藏 GitLab 顶部导航与左侧栏（可 `--keep-fixed` 保留）
- **超长页面保护**：`--max-screens` 兜底，避免大仓库文件树无限滚动
- **分章节 Word 文档**：python-docx 按审计维度分章，每张截图独占一页（或 `--continuous` 连续排列）
- **DPI 预处理**：PIL 写入 96 DPI 元数据，避免 Word 自动压缩模糊
- **内网友好**：依赖支持离线安装，Chromium 可离线部署，默认忽略自签名证书错误

---

## 内网环境开发工具

| 工具 | 版本要求 | 用途 | 内网安装方式 |
|------|---------|------|-------------|
| Python | ≥ 3.9 | 运行环境 | 系统包管理器或离线安装包 |
| pip | 随 Python | 包管理 | 配置内网 PyPI 镜像或离线 whl |
| Playwright (Python) | ≥ 1.40 | 浏览器自动化 | `pip install playwright`（离线 whl） |
| Chromium 浏览器 | 由 Playwright 管理 | 无头渲染 | 见下方"Chromium 离线安装" |
| python-docx | ≥ 1.0 | Word 文档生成 | `pip install python-docx`（离线 whl） |
| Pillow | ≥ 10.0 | 图像 DPI 预处理 | `pip install Pillow`（离线 whl） |
| requests | ≥ 2.28 | 调用 GitLab API | `pip install requests`（离线 whl） |

### Chromium 离线安装方案（三选一）

1. **外网预下载 + 内网拷贝**：在外网机器执行 `playwright install chromium`，将 `~/.cache/ms-playwright/` 整个目录打包拷贝到内网机器同路径（或设置 `PLAYWRIGHT_BROWSERS_PATH` 环境变量指向拷贝位置）
2. **内网 HTTP 镜像**：设置环境变量 `PLAYWRIGHT_DOWNLOAD_HOST=http://内网镜像地址` 后执行 `playwright install chromium`
3. **系统 Chromium + 手动指定**：使用内网已装的系统 Chromium，通过 `--executable-path` 指定路径（需版本兼容）

### pip 依赖离线安装

- **方式 A（推荐）**：在外网机器 `pip download -d ./wheels -r requirements.txt`，将 `./wheels` 拷入内网后 `pip install --no-index --find-links=./wheels -r requirements.txt`
- **方式 B**：配置内网 PyPI 镜像（如 devpi、Nexus）后直接 `pip install`

---

## 安装

```bash
# 在线安装
pip install -e .

# 离线安装（内网）
pip install --no-index --find-links=./wheels -r requirements.txt
pip install --no-index --find-links=./wheels -e .

# 安装 Chromium（在线环境）
playwright install chromium
```

---

## 快速开始

```bash
# 基本用法：截取所有分支文件树 + Tags 列表 + 各 Tag 的 commit
gitlabshot https://gitlab.internal/group/project --token <PAT> -o audit.docx

# 限定分支
gitlabshot https://gitlab.internal/group/project --token <PAT> \
  --branch main --branch develop -o audit.docx

# 追加指定 Tag 的 commit 上下文（该 tag 及后两个 commit，共 3 个详情页）
gitlabshot https://gitlab.internal/group/project --token <PAT> \
  --context-tag v1.2.0 -o audit.docx

# 切换上下文方向：取更旧的两个 commit
gitlabshot https://gitlab.internal/group/project --token <PAT> \
  --context-tag v1.0 --context-direction older -o audit.docx

# 使用内网已装的系统 Chromium
gitlabshot https://gitlab.internal/group/project --token <PAT> \
  --executable-path /usr/bin/chromium-browser -o audit.docx
```

---

## CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `project_url` | （必填） | GitLab 项目地址，如 `https://gitlab.internal/group/subgroup/project` |
| `--token` | （必填*） | Personal Access Token，也可用环境变量 `GITLABSHOT_TOKEN` |
| `-o, --output` | `audit.docx` | 输出 docx 路径 |
| `--viewport` | `1440x900` | 视口尺寸，格式 `WxH` |
| `--wait` | `800` | 每屏滚动后等待毫秒 |
| `--max-screens` | `20` | 单页最大屏数上限，防止超长页面 |
| `--keep-fixed` | `False` | 保留 GitLab 固定元素（不注入隐藏 CSS） |
| `--continuous` | `False` | 连续排列（同子节内截图不分页，子节/章节间仍分页） |
| `--format` | `png` | 图片格式：`png` 或 `jpeg` |
| `--quality` | `85` | JPEG 质量（PNG 忽略） |
| `--margin` | `0.5` | Word 页边距（英寸） |
| `--dpi` | `96` | 截图 DPI 元数据 |
| `--branch` | （空） | 指定分支（可多次传入），不传则截取所有分支 |
| `--context-tag` | （空） | 指定 tag 做 commit 上下文截图 |
| `--context-direction` | `newer` | 上下文方向：`newer`（更新的 commit）或 `older`（更旧的 commit） |
| `--executable-path` | （空） | 指定系统 Chromium 路径 |

\* `--token` 与环境变量 `GITLABSHOT_TOKEN` 至少提供一个，缺失时退出码 1。公开项目仍要求 token（统一认证流程）。

### 环境变量

| 变量 | 说明 |
|------|------|
| `GITLABSHOT_TOKEN` | Personal Access Token（与 `--token` 等价） |
| `PLAYWRIGHT_BROWSERS_PATH` | 指向预下载的 Chromium 目录 |

---

## 工作流程

1. **验证 token**：调用 `GET /api/v4/user` 携带 `PRIVATE-TOKEN`，401 则退出码 5；成功获取用户名
2. **获取项目元数据**：`GET /projects/{url_encoded_path}` 拿到 `id` 与 `default_branch`
3. **启动浏览器**：无头 Chromium，注入反检测脚本，`ignore_https_errors=True`
4. **建立网页会话**：访问 `/users/sign_in`，用户名填 `#user_login`、token 填 `#user_password`，提交登录
5. **按章节截图**（每章为 Word 的 Heading 1）：
   - **分支文件树**：每个分支一个 Heading 2，截取 `/{project}/tree/{branch}`
   - **Tags 列表**：截取 `/{project}/-/tags`
   - **Tag Commits**：每个 tag 一个 Heading 2，截取其 commit 详情页 `/{project}/-/commit/{sha}`
   - **Context（可选）**：Heading 2 说明 + 每个 commit 的 Heading 3 标注（含 short SHA 与方向标记），截取目标 tag commit 及相邻 2 个 commit 详情页
6. **生成 Word**：python-docx 按章节插入截图，PIL 预处理 DPI，每张图独占一页

每张截图前：移除 `img` 的 `loading` 属性 → 预滚动触发懒加载 → 等 `networkidle` → 回滚顶部 → 重新读 `scrollHeight` → 注入隐藏 CSS（除非 `--keep-fixed`）→ 按视口高度逐屏 `full_page=False` 截图。

---

## Word 文档结构

```
Heading 1  分支文件树
  Heading 2  <分支名>
    [截图]（每张独占一页）
  Heading 2  <分支名>
    ...
Heading 1  Tags 列表
  [截图]
Heading 1  Tag Commits
  Heading 2  <tag 名>
    [截图]
  ...
Heading 1  Context: <tag>          （仅指定 --context-tag 时）
  Heading 2  说明：<tag> 的 commit 及后两个 commit（方向：newer）
  Heading 3  target (<short_sha>)
    [截图]
  Heading 3  newer 1 (<short_sha>)
    [截图]
  Heading 3  newer 2 (<short_sha>)
    [截图]
```

- 默认每张截图后分页；`--continuous` 时同一 Heading 2 内不分页，但子节/章节间仍分页
- 空章节自动跳过，不插入空标题

---

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 参数错误（缺项目地址或 token） |
| 2 | 导航失败 / 项目地址不可达 / 文档生成失败 |
| 3 | 未捕获到任何截图（全部章节为空） |
| 4 | Chromium 缺失 |
| 5 | Token 无效或网页登录失败 |

API 持续失败（429/5xx 重试 3 次仍失败）时跳过对应章节并警告，继续其他章节；指定 `--context-tag` 不存在时跳过 context 章节并警告。

---

## 项目结构

```
gitlabshot/
├── cli.py            # CLI 入口与主编排
├── config.py         # Config 数据类（所有可调参数及默认值）
├── gitlab_api.py     # GitLab REST API 客户端（token、项目、分支、tag、commit）
├── gitlab_auth.py    # 网页会话建立（token→用户名→表单登录）
├── capture.py        # Playwright 逐视口截图核心
├── preprocess.py     # 图像 DPI 预处理
└── docx_writer.py    # Word 文档生成
pyproject.toml        # 依赖声明与命令入口
requirements.txt      # 离线 pip download 依赖清单
```

---

## 安全提示

- **Token 脱敏**：所有日志中 token 仅显示前 4 位 + `***`，不输出完整 token
- **自签名证书**：浏览器上下文默认 `ignore_https_errors=True`，API 请求默认 `verify=False`，内网自签名证书不阻断流程
- 如需启用 SSL 校验，修改 `Config.verify_ssl` 与 `ignore_https_errors`

---

## 许可证

本项目仅用于内网 GitLab 仓库审计归档场景。

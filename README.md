# gitlabshot — GitLab 仓库审计逐屏截图转 Word 工具

在内网 GitLab 环境下，对代码仓库进行审计/统计归档：自动截取**主线、送测产品基线版本、送测产品版本发布时间、送测产品版本标签、其它分支**共 5 类页面，按章节合并到 Word 文档。

与"全页面长截图"方案不同，本工具按**浏览器视口高度逐屏截图**（`full_page=False`），每张图高度不超过一屏，粘贴到 Word 后无需缩放、阅读体验好；每张截图顶部自动注入**模拟浏览器地址栏**（仅显示 `https://...` 文本，无图标），便于审计时确认页面来源。

---

## 功能特性

- **5 类审计章节**：主线 / 送测产品基线版本 / 送测产品版本发布时间 / 送测产品版本标签 / 分支
- **YAML 配置文件**：通过 `--config` 集中管理项目地址、token、基线 tag、发布标签等，命令行参数优先级更高
- **Token + 用户名密码回退认证**：API 用 PAT；网页会话优先 `private_token` URL 参数 + Basic Auth，失败回退用户名+密码表单登录
- **逐视口截图**：Playwright 无头 Chromium 按视口高度滚动，每屏单独保存
- **模拟地址栏注入**：每节首屏顶部显示 URL 文本（不含 token，无 favicon）
- **懒加载处理**：截图前移除 `loading` 属性、预滚动触发加载、等待 `networkidle`
- **固定元素隐藏**：默认注入 CSS 隐藏 GitLab 顶部导航与左侧栏（可 `--keep-fixed` 保留）
- **超长页面保护**：`--max-screens` 兜底；commits 类页面用 `--commit-screens` 限定只截前几屏（3-5 个提交）
- **分章节 Word 文档**：python-docx 按审计维度分章，每张截图独占一页（或 `--continuous` 连续排列）
- **DPI 预处理**：PIL 写入 96 DPI 元数据，避免 Word 自动压缩模糊
- **诊断友好**：每步截图前打印完整访问路径；失败时打印具体原因
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
| PyYAML | ≥ 6.0 | 配置文件解析 | `pip install pyyaml`（离线 whl） |

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

## 5 类审计章节

| 序号 | 章节 | 截图内容 | URL 模式 |
|------|------|----------|----------|
| 1 | 主线 | master 分支整页文件树 | `<仓库根 URL>` |
| 2 | 送测产品基线版本 | 基线 tag 的 commit A 之后第2个 commit C | `/-/commits/<C>` |
| 3 | 送测产品版本发布时间 | 配置的 release_tag | `/-/commits/<release_tag>` |
| 4 | 送测产品版本标签 | 标签列表第一页 | `/-/tags` |
| 5 | 分支 | 除 master 外的其它分支 | `/-/tree/<branch>` |

**产品基线逻辑**：取 `baseline_tag` 的 commit A → 取 A 之后（时间更晚）的第 2 个 commit C → 打开 `/-/commits/C`（页面顶部显示 C，其下为中间 commit，再下为 A，共前 3 个提交）。若基线 tag 不存在，改用初始提交（root）之后的第 2 个 commit。

---

## 快速开始

### 方式一：配置文件（推荐）

参考 `config.example.yml` 创建配置文件：

```yaml
project_url: "https://gitlab.linx-info.cd/group/subgroup/project"
token: ""                              # 建议留空，用环境变量
baseline_tag: "20250901_Release"
release_tag: "20260622_Release"
executable_path: "/usr/bin/google-chrome"
output: "audit.docx"
```

运行：
```bash
export GITLABSHOT_TOKEN="glpat-xxxx"
gitlabshot --config config.yml
```

### 方式二：纯命令行

```bash
# 基本用法（5 类章节全截）
gitlabshot https://gitlab.internal/group/project \
  --token <PAT> --executable-path /usr/bin/google-chrome -o audit.docx

# 指定基线 tag 与发布标签
gitlabshot https://gitlab.internal/group/project --token <PAT> \
  --baseline-tag 20250901_Release \
  --release-tag 20260622_Release \
  --executable-path /usr/bin/google-chrome -o audit.docx

# 网页认证回退：token 方式失败时用用户名+密码
export GITLABSHOT_USERNAME="yourname"
export GITLABSHOT_PASSWORD="yourpass"
gitlabshot https://gitlab.internal/group/project --token <PAT> \
  --executable-path /usr/bin/google-chrome -o audit.docx
```

---

## 配置文件字段

`config.example.yml` 含全部可配置项。优先级：**命令行参数 > 配置文件 > 环境变量 > 默认值**。

| 字段 | 说明 |
|------|------|
| `project_url` | GitLab 项目地址（必填） |
| `token` | Personal Access Token（建议留空用环境变量） |
| `baseline_tag` | 送测产品基线 tag（默认 `20250901_Release`） |
| `release_tag` | 送测产品版本发布标签 |
| `username` / `password` | 网页登录回退凭证（建议用环境变量） |
| `executable_path` | Chromium 路径 |
| `output` | 输出 docx 路径 |
| `viewport` | 视口尺寸 `WxH` |
| `wait` | 每屏等待毫秒 |
| `max_screens` | 长页面最大屏数 |
| `commit_screens` | commits 页面截图屏数（默认 1） |
| `format` / `quality` / `dpi` | 图片格式、JPEG 质量、DPI |
| `margin` | Word 页面边距（英寸） |
| `keep_fixed` | 是否保留 GitLab 固定元素 |
| `continuous` | 同子节内截图是否连续排列 |

---

## CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `project_url` | （必填） | GitLab 项目地址，可由配置文件提供 |
| `--config` | （空） | YAML 配置文件路径 |
| `--token` | （必填*） | Personal Access Token，也可用环境变量 `GITLABSHOT_TOKEN` 或配置文件 |
| `-o, --output` | `audit.docx` | 输出 docx 路径 |
| `--viewport` | `1440x900` | 视口尺寸，格式 `WxH` |
| `--wait` | `800` | 每屏滚动后等待毫秒 |
| `--max-screens` | `20` | 单页最大屏数上限，防止超长页面 |
| `--commit-screens` | `1` | commits 类页面截图屏数（1 屏约 3-5 个提交） |
| `--baseline-tag` | `20250901_Release` | 产品基线参考标签 |
| `--release-tag` | （空） | 送测产品版本发布标签 |
| `--keep-fixed` | `False` | 保留 GitLab 固定元素（不注入隐藏 CSS） |
| `--continuous` | `False` | 连续排列（同子节内截图不分页，子节/章节间仍分页） |
| `--format` | `png` | 图片格式：`png` 或 `jpeg` |
| `--quality` | `85` | JPEG 质量（PNG 忽略） |
| `--margin` | `0.5` | Word 页边距（英寸） |
| `--dpi` | `96` | 截图 DPI 元数据 |
| `--branch` | （空） | 指定分支（可多次传入），不传则截取所有分支 |
| `--executable-path` | （空） | 指定系统 Chromium 路径 |
| `--username` | （空） | 网页登录回退用户名，也可用环境变量 `GITLABSHOT_USERNAME` |
| `--password` | （空） | 网页登录回退密码，也可用环境变量 `GITLABSHOT_PASSWORD` |

\* `--token` 至少需通过命令行、配置文件或环境变量之一提供，缺失时退出码 1。

### 环境变量

| 变量 | 说明 |
|------|------|
| `GITLABSHOT_TOKEN` | Personal Access Token |
| `GITLABSHOT_USERNAME` | 网页登录回退用户名 |
| `GITLABSHOT_PASSWORD` | 网页登录回退密码 |
| `PLAYWRIGHT_BROWSERS_PATH` | 指向预下载的 Chromium 目录 |

---

## 工作流程

1. **加载配置**：读取 `--config` 指定的 YAML（可选），合并命令行参数
2. **验证 token**：调用 `GET /api/v4/user` 携带 `PRIVATE-TOKEN`，401 则退出码 5；成功获取用户名
3. **获取项目元数据**：`GET /projects/{url_encoded_path}` 拿到 `id` 与 `default_branch`
4. **启动浏览器**：无头 Chromium，注入反检测脚本，`ignore_https_errors=True`，注入 Basic Auth 凭证
5. **建立网页会话**：优先 `private_token` URL 参数 + Basic Auth 探测，失败回退用户名+密码表单登录
6. **按 5 类章节截图**（每章为 Word 的 Heading 1）：
   - **主线**：截仓库根 URL
   - **送测产品基线版本**：取基线 tag commit A 后第2个 commit C，截 `/-/commits/C`
   - **送测产品版本发布时间**：截 `/-/commits/<release_tag>`
   - **送测产品版本标签**：截 `/-/tags` 第一页
   - **分支**：截除 master 外各分支的 `/-/tree/<branch>`
7. **生成 Word**：python-docx 按章节插入截图，PIL 预处理 DPI，每张图独占一页

每张截图前：打印访问路径 → 注入模拟地址栏（显示 URL 文本）→ 移除 `img` 的 `loading` 属性 → 预滚动触发懒加载 → 等 `networkidle` → 回滚顶部 → 重新读 `scrollHeight` → 注入隐藏 CSS（除非 `--keep-fixed`）→ 按视口高度逐屏 `full_page=False` 截图。失败时打印具体原因并跳过。

---

## Word 文档结构

```
Heading 1  主线
  Heading 2  master
    [截图]（首屏顶部含模拟地址栏）
    [截图]（后续屏）
    ...
Heading 1  送测产品基线版本
  Heading 2  <baseline_tag>
    [截图]
Heading 1  送测产品版本发布时间
  Heading 2  <release_tag>
    [截图]
Heading 1  送测产品版本标签
  [截图]
Heading 1  分支
  Heading 2  <分支名>
    [截图]
  Heading 2  <分支名>
    ...
```

- 默认每张截图后分页；`--continuous` 时同一 Heading 2 内不分页，但子节/章节间仍分页
- 空章节自动跳过，不插入空标题

---

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 参数错误（缺项目地址或 token） |
| 2 | 项目地址不可达 / 文档生成失败 |
| 3 | 未捕获到任何截图（全部章节为空） |
| 4 | Chromium 缺失 |
| 5 | Token 无效或网页登录失败 |

API 持续失败（429/5xx 重试 3 次仍失败）时跳过对应章节并警告，继续其他章节。

---

## 项目结构

```
gitlabshot/
├── cli.py            # CLI 入口与主编排（5 类章节、配置文件加载）
├── config.py         # Config 数据类（所有可调参数及默认值）
├── config_loader.py  # YAML 配置文件加载模块
├── gitlab_api.py     # GitLab REST API 客户端（token、项目、分支、tag、commit、root commit）
├── gitlab_auth.py    # 网页会话建立（private_token / Basic Auth / 表单登录回退）
├── capture.py        # Playwright 逐视口截图核心（含模拟地址栏注入）
├── preprocess.py     # 图像 DPI 预处理
└── docx_writer.py    # Word 文档生成
config.example.yml    # 配置文件示例
pyproject.toml        # 依赖声明与命令入口
requirements.txt      # 离线 pip download 依赖清单
```

---

## 安全提示

- **Token 脱敏**：所有日志中 token 仅显示前 4 位 + `***`，不输出完整 token
- **截图不含 token**：注入的模拟地址栏与日志打印的访问路径均使用不含 `private_token` 的原始 URL
- **密码用环境变量**：`--username`/`--password` 建议用环境变量传入，避免出现在 shell history
- **自签名证书**：浏览器上下文默认 `ignore_https_errors=True`，API 请求默认 `verify=False`，内网自签名证书不阻断流程
- 如需启用 SSL 校验，修改 `Config.verify_ssl` 与 `ignore_https_errors`

---

## 许可证

本项目仅用于内网 GitLab 仓库审计归档场景。

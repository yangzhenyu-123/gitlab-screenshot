# gitlabshot — GitLab 仓库审计逐屏截图工具

在内网 GitLab 环境下，对代码仓库进行审计/统计归档：自动截取**主线、送测产品基线版本、送测产品版本发布时间、送测产品版本标签、其它分支**共 5 类页面，按命名规范直接保存为 PNG 文件。

与"全页面长截图"方案不同，本工具按**浏览器视口高度逐屏截图**（`full_page=False`），每张图高度不超过一屏；每张截图顶部自动注入**模拟浏览器地址栏**（仅显示 `https://...` 文本，无图标），便于审计时确认页面来源。

---

## 功能特性

- **直接保存 PNG 文件**：按命名规范 `{包名}_{类型}{序号}.png` 保存，序号两位 01-99
- **5 类审计截图**：主线 / 送测产品基线版本 / 送测产品版本发布时间 / 送测产品版本标签 / 分支
- **YAML 配置文件**：通过 `--config` 集中管理项目地址、token、基线 tag、发布标签等，命令行参数优先级更高
- **Token + 用户名密码双认证**：API 用 PAT 调用；网页会话用用户名+密码表单登录（token 方式的网页认证在内网不可用，已移除）
- **逐视口截图**：Playwright 无头 Chromium 按视口高度滚动，每屏单独保存
- **模拟地址栏注入**：每节首屏顶部显示 URL 文本（不含 token，无 favicon）
- **懒加载处理**：截图前移除 `loading` 属性、预滚动触发加载、等待 `networkidle`
- **固定元素隐藏**：默认注入 CSS 隐藏 GitLab 顶部导航与左侧栏（可 `--keep-fixed` 保留）
- **超长页面保护**：`--max-screens` 兜底；commits 类页面用 `--commit-screens` 限定只截前几屏（3-5 个提交）
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

## 5 类审计截图与文件命名

### 截图类型

| 序号 | 类型 | 截图内容 | URL 模式 |
|------|------|----------|----------|
| 1 | master | master 分支整页文件树 | `<仓库根 URL>` |
| 2 | baseline | 基线 tag 的 commit A 之后第2个 commit C | `/-/commits/<C>` |
| 3 | release | 配置的 release_tag | `/-/commits/<release_tag>` |
| 4 | tag | 标签列表第一页 | `/-/tags` |
| 5 | `{分支名}` | 除 master 外的其它分支 | `/-/tree/<branch>` |

**产品基线逻辑**：取 `baseline_tag` 的 commit A → 取 A 之后（时间更晚）的第 2 个 commit C → 打开 `/-/commits/C`（页面顶部显示 C，其下为中间 commit，再下为 A，共前 3 个提交）。若基线 tag 不存在，改用初始提交（root）之后的第 2 个 commit。

### 文件命名规范

截图直接保存为 PNG 文件，命名格式：`{包名}_{类型}{序号}.png`

| 类型 | 格式 | 示例 |
|------|------|------|
| master 分支 | `{包名}_master{NN}.png` | `anaconda_master01.png` |
| baseline | `{包名}_baseline{NN}.png` | `anaconda_baseline01.png` |
| release | `{包名}_release{NN}.png` | `anaconda_release01.png` |
| tag | `{包名}_tag{NN}.png` | `anaconda_tag01.png` |
| 其他分支 | `{包名}_{分支名}{NN}.png` | `anaconda_ztbug-1323-zyyang01.png` |

- 序号固定两位，从 `01` 递增，上限 `99`（超过 99 张的多余截图将被忽略并警告）
- 包名默认取项目路径末段（如 `.../httpd` → `httpd`），可用 `--pkg-name` 覆盖

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
output_dir: "./screenshots"
pkg_name: ""                           # 留空则取项目路径末段
# username/password 建议用环境变量传入，避免明文
```

运行：
```bash
export GITLABSHOT_TOKEN="glpat-xxxx"        # API 认证
export GITLABSHOT_USERNAME="yourname"       # 网页登录
export GITLABSHOT_PASSWORD="yourpass"       # 网页登录
gitlabshot --config config.yml
```

### 方式二：纯命令行

```bash
# 基本用法（5 类截图全截，保存到 ./screenshots）
export GITLABSHOT_USERNAME="yourname"
export GITLABSHOT_PASSWORD="yourpass"
gitlabshot https://gitlab.internal/group/project \
  --token <PAT> --executable-path /usr/bin/google-chrome \
  -o ./screenshots

# 指定基线 tag 与发布标签，自定义包名
gitlabshot https://gitlab.internal/group/project --token <PAT> \
  --baseline-tag 20250901_Release \
  --release-tag 20260622_Release \
  --pkg-name myapp \
  --executable-path /usr/bin/google-chrome -o ./out
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
| `username` / `password` | 网页登录凭证（必填，建议用环境变量） |
| `executable_path` | Chromium 路径 |
| `output_dir` | 截图输出目录（默认 `.`） |
| `pkg_name` | 文件名前缀（包名），留空则取项目路径末段 |
| `viewport` | 视口尺寸 `WxH` |
| `wait` | 每屏等待毫秒 |
| `max_screens` | 长页面最大屏数 |
| `commit_screens` | commits 页面截图屏数（默认 1） |
| `format` / `quality` | 图片格式、JPEG 质量 |
| `keep_fixed` | 是否保留 GitLab 固定元素 |

---

## CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `project_url` | （必填） | GitLab 项目地址，可由配置文件提供 |
| `--config` | （空） | YAML 配置文件路径 |
| `--token` | （必填*） | Personal Access Token，也可用环境变量 `GITLABSHOT_TOKEN` 或配置文件 |
| `-o, --output-dir` | `.` | 截图文件输出目录 |
| `--pkg-name` | （项目路径末段） | 文件名前缀（包名） |
| `--viewport` | `1440x900` | 视口尺寸，格式 `WxH` |
| `--wait` | `800` | 每屏滚动后等待毫秒 |
| `--max-screens` | `20` | 单页最大屏数上限，防止超长页面 |
| `--commit-screens` | `1` | commits 类页面截图屏数（1 屏约 3-5 个提交） |
| `--baseline-tag` | `20250901_Release` | 产品基线参考标签 |
| `--release-tag` | （空） | 送测产品版本发布标签 |
| `--keep-fixed` | `False` | 保留 GitLab 固定元素（不注入隐藏 CSS） |
| `--format` | `png` | 图片格式：`png` 或 `jpeg` |
| `--quality` | `85` | JPEG 质量（PNG 忽略） |
| `--branch` | （空） | 指定分支（可多次传入），不传则截取所有分支 |
| `--executable-path` | （空） | 指定系统 Chromium 路径 |
| `--username` | （必填） | 网页登录用户名，也可用环境变量 `GITLABSHOT_USERNAME` 或配置文件 |
| `--password` | （必填） | 网页登录密码，也可用环境变量 `GITLABSHOT_PASSWORD` 或配置文件 |

\* `--token` 用于 API 调用，至少需通过命令行、配置文件或环境变量之一提供。`--username`/`--password` 用于网页登录，必填。缺失时退出码 1。

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
4. **启动浏览器**：无头 Chromium，注入反检测脚本，`ignore_https_errors=True`
5. **建立网页会话**：用用户名+密码提交 GitLab 登录表单，登录成功后 cookie 维持后续页面访问（token 不用于网页认证）
6. **按 5 类截图并保存文件**：
   - **master**：截仓库根 URL，保存为 `{包名}_master{NN}.png`
   - **baseline**：取基线 tag commit A 后第2个 commit C，截 `/-/commits/C`，保存为 `{包名}_baseline{NN}.png`
   - **release**：截 `/-/commits/<release_tag>`，保存为 `{包名}_release{NN}.png`
   - **tag**：截 `/-/tags` 第一页，保存为 `{包名}_tag{NN}.png`
   - **分支**：截除 master 外各分支的 `/-/tree/<branch>`，保存为 `{包名}_{分支名}{NN}.png`

每张截图前：打印访问路径 → 注入模拟地址栏（显示 URL 文本）→ 移除 `img` 的 `loading` 属性 → 预滚动触发懒加载 → 等 `networkidle` → 回滚顶部 → 重新读 `scrollHeight` → 注入隐藏 CSS（除非 `--keep-fixed`）→ 按视口高度逐屏 `full_page=False` 截图。失败时打印具体原因并跳过。

---

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 参数错误（缺项目地址、token 或用户名密码） |
| 2 | 项目地址不可达 |
| 3 | 未捕获到任何截图 |
| 4 | Chromium 缺失 |
| 5 | Token 无效或网页登录失败 |

API 持续失败（429/5xx 重试 3 次仍失败）时跳过对应截图类型并警告，继续其它类型。

---

## 项目结构

```
gitlabshot/
├── cli.py            # CLI 入口与主编排（5 类截图、配置文件加载、文件命名）
├── config.py         # Config 数据类（所有可调参数及默认值）
├── config_loader.py  # YAML 配置文件加载模块
├── gitlab_api.py     # GitLab REST API 客户端（token、项目、分支、tag、commit、root commit）
├── gitlab_auth.py    # 网页会话建立（用户名+密码表单登录）
├── capture.py        # Playwright 逐视口截图核心（含模拟地址栏注入）
├── saver.py          # 截图文件按命名规范保存（{包名}_{类型}{NN}.png）
config.example.yml    # 配置文件示例
pyproject.toml        # 依赖声明与命令入口
requirements.txt      # 离线 pip download 依赖清单
```

---

## 安全提示

- **Token 脱敏**：所有日志中 token 仅显示前 4 位 + `***`，不输出完整 token
- **截图不含敏感信息**：注入的模拟地址栏与日志打印的访问路径均为原始 URL，不含 token 或密码
- **密码用环境变量**：`--username`/`--password` 建议用环境变量传入，避免出现在 shell history
- **自签名证书**：浏览器上下文默认 `ignore_https_errors=True`，API 请求默认 `verify=False`，内网自签名证书不阻断流程
- 如需启用 SSL 校验，修改 `Config.verify_ssl` 与 `ignore_https_errors`

---

## 许可证

本项目仅用于内网 GitLab 仓库审计归档场景。

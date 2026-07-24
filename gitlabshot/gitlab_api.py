"""GitLab REST API 客户端模块。

封装 GitLab v4 API 调用，提供项目元数据查询能力，用于定位审计截图目标。
所有请求携带 PRIVATE-TOKEN header，base 为 {base_url}/api/v4。
"""
import time
from urllib.parse import quote

import requests

from gitlabshot.config import Config


class InvalidTokenError(Exception):
    """Token 无效或已过期（HTTP 401）。"""


class TagNotFoundError(Exception):
    """指定 tag 不存在（HTTP 404）。"""


class APIError(Exception):
    """通用 GitLab API 错误。"""


class GitLabAPIClient:
    """GitLab REST API 客户端。

    所有请求携带 PRIVATE-TOKEN header，verify_ssl 控制证书校验（默认 False，
    适配内网自签名证书）；对 429/5xx 进行有限次递增重试。
    """

    # 429 或 5xx 重试 3 次，间隔递增 1s / 2s / 4s
    _MAX_RETRIES = 3
    _RETRY_BACKOFF = (1, 2, 4)

    def __init__(self, base_url: str, token: str, verify_ssl: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_base = self.base_url + "/api/v4"
        self.token = token
        self.verify_ssl = verify_ssl
        self._headers = {"PRIVATE-TOKEN": token}

    @classmethod
    def from_config(cls, config: Config) -> "GitLabAPIClient":
        """从 Config 构建客户端（取 base_url / token / verify_ssl）。"""
        return cls(
            base_url=config.base_url,
            token=config.token,
            verify_ssl=config.verify_ssl,
        )

    # ------------------------------------------------------------------
    # 内部请求
    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, params=None) -> requests.Response:
        """统一请求入口：拼 URL、带 header、verify、重试。

        429 或 5xx 重试 3 次（间隔 1s / 2s / 4s），仍失败抛 APIError；网络异常
        直接抛 APIError。其余状态码（含 2xx 与 4xx）原样返回 Response，由调用方
        按业务判定（如 401→InvalidTokenError、404→TagNotFoundError）。
        """
        url = self.api_base + path
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=self._headers,
                    params=params,
                    verify=self.verify_ssl,
                )
            except requests.RequestException as exc:
                raise APIError(f"请求 {method} {url} 网络异常: {exc}") from exc

            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt < self._MAX_RETRIES:
                    time.sleep(self._RETRY_BACKOFF[attempt])
                    continue
                raise APIError(
                    f"{method} {url} 重试 {self._MAX_RETRIES} 次仍失败: HTTP {resp.status_code}"
                )

            return resp

        # 理论不可达
        raise APIError(f"请求 {method} {url} 失败")

    # ------------------------------------------------------------------
    # 业务方法
    # ------------------------------------------------------------------
    def verify_token(self) -> str:
        """GET /user 验证 token；401 抛 InvalidTokenError，成功返回 username。"""
        resp = self._request("GET", "/user")
        if resp.status_code == 401:
            raise InvalidTokenError("Token 无效或已过期")
        if not resp.ok:
            raise APIError(f"验证 token 失败: HTTP {resp.status_code}")
        return resp.json().get("username", "")

    def get_project(self, url_encoded_path: str) -> dict:
        """GET /projects/{url_encoded_path}，返回含 id 与 default_branch 的 dict。

        url_encoded_path 形如 group%2Fsubgroup%2Fproject，直接拼 URL（不再编码）。
        """
        resp = self._request("GET", f"/projects/{url_encoded_path}")
        if not resp.ok:
            raise APIError(f"获取项目失败: HTTP {resp.status_code}")
        return resp.json()

    def list_branches(self, project_id: int) -> list[str]:
        """翻页 GET /projects/{id}/repository/branches?per_page=100&page=N，返回所有分支 name。"""
        names: list[str] = []
        page = 1
        while True:
            resp = self._request(
                "GET",
                f"/projects/{project_id}/repository/branches",
                params={"per_page": 100, "page": page},
            )
            if not resp.ok:
                raise APIError(f"列出分支失败: HTTP {resp.status_code}")
            data = resp.json()
            if not data:
                break
            names.extend(b.get("name", "") for b in data)
            page += 1
        return names

    def list_tags(self, project_id: int) -> list[tuple[str, str]]:
        """翻页 GET /projects/{id}/repository/tags?per_page=100&page=N，返回 [(tag_name, commit.id), ...]。"""
        result: list[tuple[str, str]] = []
        page = 1
        while True:
            resp = self._request(
                "GET",
                f"/projects/{project_id}/repository/tags",
                params={"per_page": 100, "page": page},
            )
            if not resp.ok:
                raise APIError(f"列出 tag 失败: HTTP {resp.status_code}")
            data = resp.json()
            if not data:
                break
            for t in data:
                commit = t.get("commit") or {}
                result.append((t.get("name", ""), commit.get("id", "")))
            page += 1
        return result

    def get_tag_commit(self, project_id: int, tag_name: str) -> str:
        """GET /projects/{id}/repository/tags/{quote(tag_name)}；404 抛 TagNotFoundError，返回 commit.id。"""
        resp = self._request(
            "GET",
            f"/projects/{project_id}/repository/tags/{quote(tag_name, safe='')}",
        )
        if resp.status_code == 404:
            raise TagNotFoundError(f"Tag 不存在: {tag_name}")
        if not resp.ok:
            raise APIError(f"获取 tag 失败: HTTP {resp.status_code}")
        commit = resp.json().get("commit") or {}
        return commit.get("id", "")

    def list_commits(self, project_id: int, ref_name: str) -> list[tuple[str, str, str]]:
        """翻页 GET /projects/{id}/repository/commits?ref_name={ref}&per_page=100&page=N，返回 [(id, short_id, committed_date), ...]。"""
        result: list[tuple[str, str, str]] = []
        page = 1
        while True:
            resp = self._request(
                "GET",
                f"/projects/{project_id}/repository/commits",
                params={"ref_name": ref_name, "per_page": 100, "page": page},
            )
            if not resp.ok:
                raise APIError(f"列出提交失败: HTTP {resp.status_code}")
            data = resp.json()
            if not data:
                break
            for c in data:
                result.append(
                    (c.get("id", ""), c.get("short_id", ""), c.get("committed_date", ""))
                )
            page += 1
        return result

    @staticmethod
    def find_commit_context(
        commits: list[tuple[str, str, str]],
        target_sha: str,
        direction: str = "newer",
        count: int = 2,
    ) -> list[str]:
        """在 commit 列表中定位 target_sha，按方向取相邻 count 个 commit SHA。

        commits 按「最新在前」排序（index 0 最新）。direction="newer" 取比 target
        更新的 count 个（索引更小，即 i-1, i-2, ...）；direction="older" 取更旧的
        count 个（索引更大，即 i+1, i+2, ...）。target 不在列表则返回空列表；
        相邻不足 count 个则返回实际可得的。

        排序规则（从 target 向外取相邻提交，两个方向均为「接近 target → 远离 target」）：
        - newer：按时间从旧到新排列。集合中最旧的（最接近 target）排最前，最新的
          （最远离 target）排最后。
        - older：按时间从新到旧排列。集合中最新的（最接近 target）排最前，最旧的
          （最远离 target）排最后。
        """
        target_idx = -1
        for idx, c in enumerate(commits):
            if c[0] == target_sha:
                target_idx = idx
                break
        if target_idx == -1:
            return []
        if count <= 0:
            return []

        if direction == "newer":
            # 索引 i-1, i-2, ... 取相邻 count 个；切片为升索引，反转后即按时间旧→新
            start = max(0, target_idx - count)
            selected = commits[start:target_idx]
            return [c[0] for c in reversed(selected)]

        if direction == "older":
            # 索引 i+1, i+2, ... 取相邻 count 个；切片本身即按时间新→旧
            end = target_idx + 1 + count
            selected = commits[target_idx + 1 : end]
            return [c[0] for c in selected]

        return []

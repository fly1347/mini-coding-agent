"""
文件作用：
限制用户文件访问范围，提供小型文本仓库的读取、搜索、修改与内容指纹。

整体结构：
1）private / path / protected_paths：识别保留路径，拒绝越界、链接和特殊文件；
2）files / read / write / replace / search：提供受限文件工具；
3）snapshot：计算源文件指纹，用于检查改动和验证是否过期。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

MAX_FILE = 256 * 1024
MAX_FILES = 1000
PRIVATE = {".git", ".mini-agent", ".venv", "venv", "RUN_REPORT.md"}
IGNORED = {"__pycache__", ".pytest_cache"}


# 判断路径名是否属于凭据、运行证据或其他保留区域。
def private(name: str) -> bool:
    return name in PRIVATE or name == ".env" or name.startswith(".env.")


class Workspace:
    """集中维护一个 workspace 的文件边界与文本操作。"""
    # 解析工作区根目录，并在执行程序前检查目录及受保护路径。
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir() or self.root == Path("/"):
            raise ValueError("workspace must be a project directory, not /")
        self.protected_paths()  # 在启动可写子进程前，先拒绝链接等路径别名。

    # 把相对路径转换为经过越界、链接和文件类型检查的路径。
    def path(self, relative: str) -> Path:
        p = Path(relative)
        if p.is_absolute() or ".." in p.parts or any(private(x) for x in p.parts):
            raise ValueError("path must stay inside workspace; private paths are reserved")
        target = self.root / p
        for ancestor in [target, *target.parents]:
            if ancestor == self.root:
                break
            if ancestor.is_symlink():
                raise ValueError("symbolic links are not supported")
        if target.exists() and target.is_file() and target.stat().st_nlink != 1:
            raise ValueError("hard links are not supported")
        if target.exists() and not (target.is_file() or target.is_dir()):
            raise ValueError("special files are not supported")
        if not target.resolve().is_relative_to(self.root):
            raise ValueError("path escapes workspace")
        return target

    # 收集需要在沙箱中遮蔽的路径，并提前拒绝不支持的文件。
    def protected_paths(self) -> list[Path]:
        protected = []
        count = 0
        for base, dirs, files in os.walk(self.root, followlinks=False):
            for name in list(dirs) + files:
                p = Path(base) / name
                count += 1
                if count > 5000:
                    raise ValueError("workspace too large for this mini experiment (5000 entries)")
                if p.is_symlink():
                    raise ValueError(f"remove symbolic link before running: {p.relative_to(self.root)}")
                if private(name):
                    protected.append(p)
                    if name in dirs:
                        dirs.remove(name)
                elif not (p.is_dir() or p.is_file()):
                    raise ValueError("workspace contains a special file")
                elif p.is_file() and p.stat().st_nlink != 1:
                    raise ValueError("workspace contains a hard link")
        return protected

    # 列出受大小范围约束的源文件，跳过私有内容和缓存。
    def files(self) -> list[str]:
        result = []
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not private(d) and d not in IGNORED
                             and not (Path(base) / d).is_symlink())
            for name in sorted(files):
                if private(name) or name.endswith(".pyc"):
                    continue
                relative = str((Path(base) / name).relative_to(self.root))
                self.path(relative)
                result.append(relative)
                if len(result) > MAX_FILES:
                    raise ValueError("workspace exceeds 1000 source files")
        return result

    # 读取大小受限的 UTF-8 常规文件。
    def read(self, path: str) -> str:
        p = self.path(path)
        if not p.is_file() or p.stat().st_size > MAX_FILE:
            raise ValueError("expected a regular UTF-8 file of at most 256 KiB")
        return p.read_text(encoding="utf-8")

    # 创建或覆盖 workspace 内的文本文件，并返回写入信息。
    def write(self, path: str, content: str) -> dict:
        p = self.path(path)
        if len(content.encode()) > MAX_FILE:
            raise ValueError("file exceeds 256 KiB")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"path": path, "bytes": len(content.encode())}

    # 仅在旧文本唯一匹配时替换，避免误改多个位置。
    def replace(self, path: str, old: str, new: str) -> dict:
        content = self.read(path)
        if not old or content.count(old) != 1:
            raise ValueError("old text must match exactly once; read the file and retry")
        return self.write(path, content.replace(old, new, 1))

    # 返回字面文本的前 50 个匹配位置。
    def search(self, query: str) -> list[dict]:
        if not query:
            raise ValueError("query cannot be empty")
        hits = []
        for path in self.files():
            try:
                content = self.read(path)
            except (UnicodeError, ValueError):
                continue
            for n, line in enumerate(content.splitlines(), 1):
                if query in line:
                    hits.append({"path": path, "line": n, "text": line[:300]})
                    if len(hits) == 50:
                        return hits
        return hits

    # 计算源文件内容指纹，用于判断修改和验证证据是否过期。
    def snapshot(self) -> dict[str, str]:
        result = {}
        for path in self.files():
            p = self.path(path)
            if p.stat().st_size > MAX_FILE:
                raise ValueError(f"source file too large: {path}")
            result[path] = hashlib.sha256(p.read_bytes()).hexdigest()
        return result

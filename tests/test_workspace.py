"""
文件作用：
验证文件工具能读写和搜索，并拒绝越界、链接及特殊文件。

整体结构：
1）setUp / 正常用例：创建临时 Workspace，串联新建、精确替换、搜索和文件枚举；
2）路径用例：拒绝越界、绝对路径、保留区域、符号链接和硬链接；
3）内容用例：替换目标不唯一时保留原文，私有配置内容不得出现在搜索结果中；
4）特殊文件用例：初始化后再创建 FIFO，检查源码快照和写入都会拒绝，避免阻塞。

验证边界：
测试真实操作临时文件系统，不调用模型或执行沙箱；它验证的是文件工具边界，
程序启动后的进程隔离另由 test_sandbox.py 检查。
"""
from pathlib import Path
import os
import tempfile
import unittest

from mini_coding_agent.workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws = Workspace(self.root)

    # 新建嵌套路径文件并精确替换，确认搜索位置和文件清单反映修改后的内容。
    def test_read_search_create_replace(self):
        self.ws.write("src/app.py", "def answer():\n    return 41\n")
        self.ws.replace("src/app.py", "return 41", "return 42")
        self.assertEqual(self.ws.search("return 42")[0]["line"], 2)
        self.assertEqual(self.ws.files(), ["src/app.py"])

    # 越界、绝对路径及嵌套保留文件都必须在写入前被拒绝。
    def test_traversal_absolute_and_reserved_paths(self):
        for path in ("../escape", "/tmp/escape", ".git/config", ".mini-agent/x", "sub/.env"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.ws.write(path, "bad")

    # 依次创建符号链接和硬链接，确认已有实例与重新初始化都遵守相应检查且原文未变。
    def test_symlink_and_hardlink_rejected(self):
        self.ws.write("real", "original")
        (self.root / "alias").symlink_to(self.root / "real")
        with self.assertRaises(ValueError):
            self.ws.write("alias", "changed")
        with self.assertRaises(ValueError):
            Workspace(self.root)
        (self.root / "alias").unlink()
        (self.root / "alias").hardlink_to(self.root / "real")
        with self.assertRaises(ValueError):
            self.ws.write("real", "changed")
        self.assertEqual((self.root / "real").read_text(), "original")

    # 待替换文本出现多次时拒绝修改，防止一次替换误伤多个位置。
    def test_nonunique_edit_leaves_file_unchanged(self):
        self.ws.write("a.py", "x x")
        with self.assertRaises(ValueError):
            self.ws.replace("a.py", "x", "y")
        self.assertEqual(self.ws.read("a.py"), "x x")

    # 绕过工具写入私有配置，确认搜索仍主动过滤敏感内容。
    def test_private_content_is_not_searchable(self):
        (self.root / ".env").write_text("secret-marker")
        (self.root / "readme.txt").write_text("public")
        self.assertEqual(self.ws.search("secret-marker"), [])

    # 初始化后新出现的 FIFO 也必须被快照和写入拒绝，不能因特殊文件等待而挂住。
    def test_special_file_created_after_start_does_not_block_inventory(self):
        os.mkfifo(self.root / "pipe")
        with self.assertRaises(ValueError):
            self.ws.snapshot()
        with self.assertRaises(ValueError):
            self.ws.write("pipe", "do not block")

"""
文件作用：
验证文件工具能读写和搜索，并拒绝越界、链接及特殊文件。

整体结构：
WorkspaceTests 为每个用例创建临时目录，分别检查正常操作与边界拒绝。
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

    def test_read_search_create_replace(self):
        self.ws.write("src/app.py", "def answer():\n    return 41\n")
        self.ws.replace("src/app.py", "return 41", "return 42")
        self.assertEqual(self.ws.search("return 42")[0]["line"], 2)
        self.assertEqual(self.ws.files(), ["src/app.py"])

    def test_traversal_absolute_and_reserved_paths(self):
        for path in ("../escape", "/tmp/escape", ".git/config", ".mini-agent/x", "sub/.env"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.ws.write(path, "bad")

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

    def test_nonunique_edit_leaves_file_unchanged(self):
        self.ws.write("a.py", "x x")
        with self.assertRaises(ValueError):
            self.ws.replace("a.py", "x", "y")
        self.assertEqual(self.ws.read("a.py"), "x x")

    def test_private_content_is_not_searchable(self):
        (self.root / ".env").write_text("secret-marker")
        (self.root / "readme.txt").write_text("public")
        self.assertEqual(self.ws.search("secret-marker"), [])

    def test_special_file_created_after_start_does_not_block_inventory(self):
        os.mkfifo(self.root / "pipe")
        with self.assertRaises(ValueError):
            self.ws.snapshot()
        with self.assertRaises(ValueError):
            self.ws.write("pipe", "do not block")

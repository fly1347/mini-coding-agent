"""
文件作用：
对演示交付进行独立验收，在临时副本中运行额外断言，不改动原交付。

整体结构：
1）ACCEPTANCE / CLI_ACCEPTANCE：定义独立的行为和 CLI 检查；
2）original_methods：提取原测试方法的 AST，检查是否被改弱；
3）main：区分从零创建与旧样例修复，复制交付、添加验收测试并在沙箱中执行。
"""
import argparse
import ast
from pathlib import Path
import shutil
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from mini_coding_agent.sandbox import run_command
from mini_coding_agent.workspace import Workspace

ACCEPTANCE = '''import subprocess
import unittest
from slugify import slugify

class IndependentAcceptance(unittest.TestCase):
    def test_contract_cases(self):
        for raw, expected in [('', ''), ('!!!', ''), (' ', ''), ('Hello World', 'hello-world'),
                              ('  Hello, WORLD!!  ', 'hello-world'), ('A___B', 'a-b'),
                              ('a\\t\\nb', 'a-b'), ('A123', 'a123'), ('a--b', 'a-b'),
                              ('-a-', 'a'), ('a/b.c', 'a-b-c'), ('123', '123')]:
            with self.subTest(raw=raw):
                self.assertEqual(slugify(raw), expected)
'''
CLI_ACCEPTANCE = '''
    def test_cli_subprocess(self):
        result = subprocess.run(['python3', 'cli.py', '  Hello, WORLD!!  '],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'hello-world')
'''


def original_methods(source):
    """提取原测试类中的方法 AST，用于比较既有断言是否保留。"""
    tree = ast.parse(source)
    return {method.name: ast.dump(method) for node in tree.body if isinstance(node, ast.ClassDef)
            and node.name == "SlugifyTests" for method in node.body if isinstance(method, ast.FunctionDef)}


def main():
    """在临时沙箱副本中执行独立验收，并返回执行状态。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--cli", action="store_true")
    parser.add_argument("--created", action="store_true", help="验收空目录创建的项目（含 CLI），无原始测试 AST 可比较")
    args = parser.parse_args()
    if not args.created:
        expected = original_methods((PROJECT / "examples/slugify/test_slugify.py").read_text())
        actual = original_methods((args.workspace / "test_slugify.py").read_text())
        if any(actual.get(name) != body for name, body in expected.items()):
            raise SystemExit("Original test methods were removed or changed; inspect before accepting.")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "workspace"
        shutil.copytree(args.workspace, root, ignore=shutil.ignore_patterns(".mini-agent", "__pycache__"))
        ws = Workspace(root)
        ws.write("test_independent_acceptance.py", ACCEPTANCE + (CLI_ACCEPTANCE if args.cli or args.created else ""))
        result = run_command(ws, "python3 -m unittest discover -s . -v")
    print("Created project: independent contract and CLI checks." if args.created else "Original 3 test methods preserved (AST check).")
    print(result["output"])
    print(f"exit_code={result['exit_code']}; termination={result['termination']}")
    return 0 if result["exit_code"] == 0 and not result["termination"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

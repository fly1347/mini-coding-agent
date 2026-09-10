# Slugify 小任务

`slugify.py` 将标题变成 URL slug，标准库项目，没有第三方依赖。

开发任务：修复 slugify，使其将 ASCII 英文转小写，把连续空白和标点折叠为一个
连字符，去掉首尾连字符；空输入或只有标点时返回空字符串。仅保留 ASCII 字母和数字。
例如 `"  Hello, WORLD!!  "` → `"hello-world"`，`"A___B"` → `"a-b"`。
补充边界回归测试，不删除或弱化已有测试。可添加 CLI（仅在任务明确要求时）。

验证：`python3 -m unittest discover -s . -v`。
这是故意有 bug 的初始 fixture，请复制到独立 workspace 再运行 Agent。

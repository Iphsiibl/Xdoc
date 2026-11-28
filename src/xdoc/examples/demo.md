# xdoc 示例报告

这是一份用来演示 xdoc 输出的示例文件。它同时包含标题、表格、代码块和列表，
所以 `xdoc read` 之后你会看到锚点（`<!-- doc:0 -->`）和表格结构。

## 一、文档结构

xdoc 把文件拆成若干「节」（section），每节带一个锚点，引用时不会张冠李戴。

- 第一级信息：标题
- 第二级信息：小节
- 表格与代码块原样保留

## 二、一个表格

| 能力 | 载体 | 说明 |
| --- | --- | --- |
| 读文件 | `xdoc read` | 命令行 |
| 读文件 | MCP 工具 `read` | 给 Agent 用 |
| 检索 | `xdoc grep` | 在文件或目录里找关键词 |

## 三、一段代码

```python
def hello(name: str) -> str:
    return f"你好，{name}"
```

## 四、怎么读它

```bash
xdoc read demo.md            # 全文
xdoc read demo.md --outline  # 只要结构
xdoc grep "锚点" demo.md     # 只看命中处
```

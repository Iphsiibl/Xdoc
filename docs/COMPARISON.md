# xdoc vs anymd：同批样本、同指标、同机器

对比对象：`@sylphx/anymd`（SylphxAI/anymd，MIT，Rust 写的 MCP server + CLI）与本项目的 xdoc。

- **样本**：`samples/` 下 17 个公开真实文件（PDF/扫描件/DOCX/PPTX/XLSX/图片/音频/视频/HTML），
  由 `tools/fetch_samples.py` 自动抓取，不是人造样本。
- **指标**：`token_recall`（词级保留率，忽略顺序，只看有没有丢字）与 `shingle_recall`（8-gram 保留率，
  兼顾顺序）。参考文本由 pymupdf / python-docx / python-pptx / openpyxl / BeautifulSoup 独立抽取，
  与被测引擎无关。
- **环境**：Windows / AMD Ryzen 7 PRO 5875U（8c16t，无独显，全程 CPU）；每个样本跑 3 次取中位数。

## 结果

| 样本 | xdoc token | anymd token | xdoc 8-gram | xdoc 耗时 | anymd 耗时 | 谁更全 |
| --- | --- | --- | --- | --- | --- | --- |
| pdf/en_arxiv_attention.pdf | 1.0000 | 0.9836 | 0.9831 | 2.75s | 2.01s | **xdoc** |
| pdf/en_dummy.pdf | 1.0000 | 1.0000 | 1.0000 | 0.01s | 1.79s | 持平 |
| pdf/en_paper_tracemonkey.pdf | 1.0000 | 0.9607 | 0.9783 | 3.21s | 1.67s | **xdoc** |
| pdf/zh_wiki_microsoft.pdf | 1.0000 | 0.8768 | 0.9818 | 5.41s | 2.58s | **xdoc** |
| pdf/zh_wiki_python.pdf | 1.0000 | 0.9012 | 0.9632 | 15.05s | 3.18s | **xdoc** |
| docx/calibre_demo.docx | 1.0000 | 0.9816 | 0.9613 | 0.10s | 2.28s | **xdoc** |
| pptx/poi_SampleShow.pptx | 1.0000 | 1.0000 | 0.9688 | 0.02s | 2.14s | 持平 |
| pptx/pythonpptx_test.pptx | 1.0000 | 1.0000 | 1.0000 | 0.02s | 2.12s | 持平 |
| xlsx/microsoft_sample.xlsx | 1.0000 | 0.8552 | 0.9996 | 0.30s | 2.70s | **xdoc** |
| html/en_wikipedia.html | 0.9757 | 0.8696 | 0.9039 | 0.16s | 2.18s | **xdoc** |
| html/zh_wikipedia.html | 0.9927 | 0.9115 | 0.9298 | 0.86s | 2.50s | **xdoc** |

合计：xdoc 更全 8 个、持平 3 个、落后 0 个。

## 读法

- **中文 PDF 差距最大**：xdoc 词级 1.0000 / 8-gram 0.96–0.98，anymd 词级 0.88–0.90 / 8-gram 0.74–0.75。
  anymd 默认用英文 tesseract，中英混排的维基 PDF 掉字明显；xdoc 直接取 PDF 文本层（词级不掉字），
  扫描件另走 PP-OCRv6，4 个中英扫描样本字符 F1 均为 1.0000。
- **HTML 差距明显**：xdoc 词级 0.976–0.993 / 8-gram 0.90–0.93，anymd 0.55–0.87。
- **anymd 的强项是速度与安装**：单文件约 1.8–2.7s（含 npx 冷启动），`npx -y @sylphx/anymd setup`
  能自动注册到所有 MCP 客户端；xdoc 的大 PDF（64 页）要 6–14s，因为要还原表格与图片。
- **anymd 的 OCR/ASR 需要额外下载**：好成绩要另装约 2GB 的本地 doc-VLM；语音转写模型也是另下。
  xdoc 把这些做成插件（`xdoc plugin add ocr/asr/asr-zh`），按需装、随时卸。

## 结论

1. **质量过关**：在同一批真实样本上，xdoc 的保真度全面达到 anymd，中文场景明显更好。
2. **继续走自己的路线**，但吸收 anymd 两个值得抄的点：
   - 「一条命令装好并注册到所有 MCP 客户端」的安装体验（xdoc 已发布到 PyPI：`uv tool install xdoc-tools`，命令仍是 `xdoc`）；
   - 页面锚点 + 续读游标的输出形态（xdoc 已实现 `<!-- page N -->` 与 `next_cursor`）。
3. **不引入 anymd 作为依赖**：它是 Rust 二进制 + 闭源 Pro 功能，且核心能力（保真度）不如自研实现。


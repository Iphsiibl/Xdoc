# xdoc 验收报告

> 由 `tools/acceptance.py` 生成，`tools/report.py` 渲染；数字全部来自真实运行。
> 运行环境：Windows / AMD Ryzen 7 PRO 5875U (8c16t，无独显，全 CPU) / Python 3.14。
> 每个样本重复 3 次取中位数（同时记录离散度）。

## 1. 文本保真（不丢信息）

判据：词级保留率（token_recall）≥ 0.99。参考文本由 pymupdf/python-docx/python-pptx/
openpyxl/BeautifulSoup 独立抽取，与被测引擎无关。Excel 的日期时间两边统一按 ISO 8601
比较，避免把格式差异当成丢字。

| 样本 | xdoc token_recall | xdoc shingle | anymd token_recall | xdoc 中位耗时 | anymd 耗时 |
| --- | --- | --- | --- | --- | --- |
| pdf/en_arxiv_attention.pdf | 1.0000 | 0.9831 | 0.9836 | 2.75s（0.65s 抖动） | 2.01 |
| pdf/en_dummy.pdf | 1.0000 | 1.0000 | 1.0 | 0.01s（0.00s 抖动） | 1.79 |
| pdf/en_paper_tracemonkey.pdf | 1.0000 | 0.9783 | 0.9607 | 3.21s（0.35s 抖动） | 1.67 |
| pdf/zh_wiki_microsoft.pdf | 1.0000 | 0.9818 | 0.8768 | 5.41s（1.08s 抖动） | 2.58 |
| pdf/zh_wiki_python.pdf | 1.0000 | 0.9632 | 0.9012 | 15.05s（1.52s 抖动） | 3.18 |
| docx/calibre_demo.docx | 1.0000 | 0.9613 | 0.9816 | 0.10s（0.01s 抖动） | 2.28 |
| pptx/poi_SampleShow.pptx | 1.0000 | 0.9688 | 1.0 | 0.02s（0.00s 抖动） | 2.14 |
| pptx/pythonpptx_test.pptx | 1.0000 | 1.0000 | 1.0 | 0.02s（0.01s 抖动） | 2.12 |
| xlsx/microsoft_sample.xlsx | 1.0000 | 0.9996 | 0.8552 | 0.30s（0.05s 抖动） | 2.7 |
| html/en_wikipedia.html | 0.9757 | 0.9039 | 0.8696 | 0.16s（0.07s 抖动） | 2.18 |
| html/zh_wikipedia.html | 0.9927 | 0.9298 | 0.9115 | 0.86s（0.51s 抖动） | 2.5 |

## 2. 结构可追溯

判据：锚点数量 == 源文件的页/张/表数量。

| 样本 | 类型 | 期望 | 实际 | 结论 |
| --- | --- | --- | --- | --- |
| pdf/en_arxiv_attention.pdf | pdf | 15 | 15 | **PASS** |
| pdf/en_dummy.pdf | pdf | 1 | 1 | **PASS** |
| pdf/en_paper_tracemonkey.pdf | pdf | 14 | 14 | **PASS** |
| pdf/scanned_en.pdf | pdf | 1 | 1 | **PASS** |
| pdf/scanned_zh.pdf | pdf | 1 | 1 | **PASS** |
| pdf/zh_wiki_microsoft.pdf | pdf | 25 | 25 | **PASS** |
| pdf/zh_wiki_python.pdf | pdf | 64 | 64 | **PASS** |
| pptx/poi_SampleShow.pptx | pptx | 2 | 2 | **PASS** |
| pptx/pythonpptx_test.pptx | pptx | 1 | 1 | **PASS** |
| xlsx/microsoft_sample.xlsx | xlsx | 1 | 1 | **PASS** |

## 3. OCR

判据：字符级 F1 ≥ 95%。指标用**无序多重集**比较（精确率/召回率/F1）：海报与扫描件
的阅读顺序本来就不确定，用编辑距离会把「顺序不同」误判成「识别错」。
候选文本只取文档里的 text 块（OCR 出来的字），不含 section 头、图片说明与资产路径。

| 样本 | 精确率 | 召回率 | F1 | 门槛 | 结论 | 输出片段 |
| --- | --- | --- | --- | --- | --- | --- |
| images/zh_easyocr_chinese.jpg | 1.0000 | 1.0000 | 1.0000 | 95% | **PASS** | 西
愚园路
东
315
309
W
Yuyuan Rd.
E |
| images/en_easyocr_english.png | 1.0000 | 1.0000 | 1.0000 | 95% | **PASS** | Reduce your risk of coronavirus infection:
Clean hands with soap and water
or al |
| pdf/scanned_zh.pdf | 1.0000 | 1.0000 | 1.0000 | 95% | **PASS** | 愚园路
西
东
315
309
W
Yuyuan Rd.
E |
| pdf/scanned_en.pdf | 1.0000 | 1.0000 | 1.0000 | 95% | **PASS** | Reduce your risk of coronavirus infection:
Clean hands with soap and water
or al |

## 4. ASR

判据：中文错字率（CER）≤ 5%；时间戳误差 ≤ 1s（时间戳真值用能量阈值独立测得，
不依赖 ASR 模型自己的输出）。

| 样本 | CER/词错率 | 门槛 | ASR 起止 | 能量法测得起止 | 起点误差 | 终点误差 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| audio/zh_funasr_example.wav | 0.0000 | 5% | 0.88–5.2s | 0.95–5.06s | 0.07s | 0.14s | **PASS** |
| audio/en_jfk.flac | 0.0435 | — | 0.0–11.0s | 0.33–10.99s | 0.33s | 0.01s | **PASS** |

- `audio/zh_funasr_example.wav` 转写：欢迎大家来体验达摩院推出的语音识别模型。

- `audio/en_jfk.flac` 转写：And so, my fellow Americans, ask not what your country can do for you. Ask what you can do for your country.

## 5. 运行期离线

判据：把 HTTP(S)/ALL_PROXY 全部指向黑洞 127.0.0.1:9，任何运行期联网都会失败或超时；
在这样的环境下仍能完成转换，即证明不依赖网络。

| 样本 | 结果 | 耗时 | 输出字符 | 备注 |
| --- | --- | --- | --- | --- |
| pdf/zh_wiki_python.pdf | **PASS** | 15.93s | 127058 |  |
| images/zh_easyocr_chinese.jpg | **PASS** | 4.03s | 56 |  |
| audio/zh_funasr_example.wav | **PASS** | 67.74s | 57 |  |
| audio/en_jfk.flac | **PASS** | 11.44s | 147 |  |

## 6. 输出格式可选

- `docx/calibre_demo.docx`：markdown=10453 字符，text=9469 字符，json=21267 字符 → **PASS**

## 7. MCP 工具面

- 暴露的工具：['read']（数量 1）→ **PASS**
  用户明确要求「单个 MCP 工具」，工具数量必须为 1。

## 8. 长文续读（max_tokens + cursor）

- `xlsx/microsoft_sample.xlsx`：分 8 段读完，累计 84137 字符，完整读取 82919 字符，覆盖率 1.015 → **PASS**


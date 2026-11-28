---
name: xdoc-read
description: Read PDF, Word, Excel, PowerPoint, images, scanned pages, audio, video, HTML/EPUB documents as faithful text through the local xdoc MCP tool. Use whenever a task needs the content of a document, spreadsheet, slide deck, image, or media transcript.
---

Read documents with the `xdoc` MCP server — one tool, `read` (stdio MCP; the same code is the `xdoc read` CLI).

**Never** hand a PDF/DOCX/XLSX/PPTX/audio/video file to the built-in file reader: most models
reject binary input, and images of pages are unreadable without OCR. Always go through `xdoc`.

## Tool

```
read(path, format="markdown", max_tokens=30000, cursor=None, pages=None, outline=False,
     grep=None, grep_regex=False, grep_context=0, grep_limit=50,
     ocr="auto", asr="auto", asr_model=None, tables="auto", images="refs", front_matter=True)
```

- `path`: a file **or a directory**. A directory is merged into one document; anchors then carry the
  file name (`<!-- file:report.pdf page 3 -->`) and the front-matter lists every file that was read
  (plus the ones that were skipped and why).
- `outline`: `true` returns only the structure — headings and anchors, no body text. Use it as the
  first call on a long document to learn its shape, then fetch the parts you need with `pages`.
  A 64-page Chinese wiki goes from ~126k chars to ~5k (4%).
- `grep`: return only the passages containing this term (literal, case-insensitive). `grep_regex`
  treats it as a regular expression, `grep_context` adds N lines around each hit, `grep_limit` caps
  how many hits come back. The front-matter reports the total number of hits even when the list is
  cut short. `grep` and `outline` cannot be combined.
- `format`: `markdown` (default, best for reading), `json` (structure/values you must query precisely),
  `text` (plainest).
- `pages`: page/slide ranges such as `1-5,8` — narrow the read instead of reading a whole book.
- `max_tokens`: cap the output (default 30000; `0` means unlimited). When the result is truncated the
  front-matter carries `truncated: true` and a `next_cursor`. To continue, call `read` again with
  `cursor: <next_cursor>` (coordinates are relative to the whole document, so chains are safe).
  Long spreadsheets come back in row-sliced chunks with the header repeated.
- `ocr` / `asr`: `auto` (default) uses the locally installed plugins; `off` disables them.
- `front_matter`: keep `true` — it carries the source path, page/slide/sheet counts, sha256,
  the cache hit/miss flag and the continuation cursor.

Errors come back as tool errors (`isError: true`) with the reason in the text (e.g. "文件不存在: …",
"无效的 cursor: …", "指定的范围 '999' 超出文档范围（文档共 64 节，可用 1-64）"). Fix the path or
install the missing plugin and retry — never treat an error message as document content.

## Recommended order (saves tokens)

1. `read(path, outline=true)` — see the structure.
2. `read(path, grep="关键词")` — only the passages that mention it.
3. `read(path, pages="7-9")` — pull only the pages you need.
4. `read(path, cursor="…")` — continue when the output is still too long.

## Missing plugins

OCR (scanned pages, images), speech-to-text (audio/video) and video frame extraction need local
plugins. If a read fails with an install command, run it and retry:

```bash
xdoc plugin add ocr      # RapidOCR / PP-OCRv6, ~280MB, CPU, Chinese+English
xdoc plugin add asr      # faster-whisper, ~730MB, general purpose
xdoc plugin add asr-zh   # FunASR Paraformer-zh, ~3.2GB, better Chinese
xdoc plugin add media    # ffmpeg, ~210MB, video frames + audio extraction
```

Everything runs offline once installed; the tool never calls a cloud service.

## Reading the output

The output is a faithful conversion, never a summary — do the extraction yourself, and quote
the source exactly (amounts, dates, IDs). Anchor lines mark the origin of each chunk:

- PDF: `<!-- page 3 -->`
- PowerPoint: `<!-- slide 2 -->`
- Excel: `<!-- sheet: 汇总 -->`
- Audio/video: `<!-- t=00:00:12 -->`
- HTML: `<!-- section:0 -->`, EPUB: `<!-- chapter:0 -->`
- Directory read: `<!-- file:report.pdf page 3 -->`

Cite these anchors when answering ("on page 3 of the PDF…", "slide 2 says…"), so the answer can
be checked against the original. Images and video frames are written next to the document under
`~/.local/share/xdoc/assets/<name>-<hash>/` and referenced by path in the output — open them when
the text alone is not enough (charts, diagrams, screenshots).

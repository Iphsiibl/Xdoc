---
name: xdoc-read
description: Read PDF, Word, Excel, PowerPoint, images, scanned pages, audio, video, HTML/EPUB documents as faithful text through the local xdoc MCP tool. Use whenever a task needs the content of a document, spreadsheet, slide deck, image, or media transcript.
---

Read documents with the `xdoc` MCP server — one tool, `read` (stdio MCP; the same code is the `xdoc read` CLI).

**Never** hand a PDF/DOCX/XLSX/PPTX/audio/video file to the built-in file reader: most models
reject binary input, and images of pages are unreadable without OCR. Always go through `xdoc`.

## Tool

```
read(path, format="markdown", max_tokens=None, cursor=None, pages=None,
     ocr="auto", asr="auto", asr_model=None, images="refs", front_matter=True)
```

- `format`: `markdown` (default, best for reading), `json` (structure/values you must query precisely),
  `text` (plainest).
- `pages`: page/slide ranges such as `1-5,8` — narrow the read instead of reading a whole book.
- `max_tokens`: cap the output; when the result is truncated the front-matter carries
  `truncated: true` and a `next_cursor`. To continue, call `read` again with
  `cursor: <next_cursor>` (coordinates are relative to the whole document, so chains are safe).
  Long spreadsheets come back in row-sliced chunks with the header repeated.
- `ocr` / `asr`: `auto` (default) uses the locally installed plugins; `off` disables them.
- `front_matter`: keep `true` — it carries the source path, page/slide/sheet counts, sha256 and
  the continuation cursor.

## Missing plugins

OCR (scanned pages, images), speech-to-text (audio/video) and video frame extraction need local
plugins. If a read fails with an install command, run it and retry:

```bash
xdoc plugin add ocr      # RapidOCR / PP-OCRv6, ~60MB, CPU, Chinese+English
xdoc plugin add asr      # faster-whisper, ~500MB, general purpose
xdoc plugin add asr-zh   # FunASR Paraformer-zh, ~2GB, better Chinese
xdoc plugin add media    # ffmpeg, ~90MB, video frames + audio extraction
```

Everything runs offline once installed; the tool never calls a cloud service.

## Reading the output

The output is a faithful conversion, never a summary — do the extraction yourself, and quote
the source exactly (amounts, dates, IDs). Anchor lines mark the origin of each chunk:

- PDF: `<!-- page 3 -->`
- PowerPoint: `<!-- slide 2 -->`
- Excel: `<!-- sheet: 汇总 -->`
- Audio/video: `<!-- t=00:00:12 -->`

Cite these anchors when answering ("on page 3 of the PDF…", "slide 2 says…"), so the answer can
be checked against the original. Images and video frames are written next to the document under
`~/.local/share/xdoc/assets/<name>-<hash>/` and referenced by path in the output — open them when
the text alone is not enough (charts, diagrams, screenshots).

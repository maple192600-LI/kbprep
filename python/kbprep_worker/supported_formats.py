"""Shared file format routing tables for diagnose, prepare, detect, and batch."""

PDF_EXTENSIONS = {".pdf"}
EPUB_EXTENSIONS = {".epub"}
EBOOK_EXTENSIONS = EPUB_EXTENSIONS | {".mobi"}
OFFICE_XML_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
LEGACY_OFFICE_EXTENSIONS = {".doc", ".ppt", ".xls"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
PLAIN_TEXT_EXTENSIONS = {".txt", ".rst", ".adoc"}
TABLE_TEXT_EXTENSIONS = {".csv", ".tsv"}
HTML_EXTENSIONS = {".html", ".htm"}
JSON_EXTENSIONS = {".json"}
NOTEBOOK_EXTENSIONS = {".ipynb"}
SUBTITLE_EXTENSIONS = {".vtt", ".srt", ".ass", ".lrc"}
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".cs", ".php", ".rb", ".swift", ".kt", ".kts", ".scala",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".sql",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif", ".svg"}

CODE_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".ps1": "powershell",
    ".bat": "bat",
    ".cmd": "batch",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "conf",
}

DIRECT_EXTENSIONS = (
    MARKDOWN_EXTENSIONS
    | PLAIN_TEXT_EXTENSIONS
    | TABLE_TEXT_EXTENSIONS
    | HTML_EXTENSIONS
    | JSON_EXTENSIONS
    | NOTEBOOK_EXTENSIONS
    | SUBTITLE_EXTENSIONS
    | CODE_EXTENSIONS
)
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
MINERU_EXTENSIONS = PDF_EXTENSIONS
SUPPORTED_EXTENSIONS = (
    DIRECT_EXTENSIONS
    | OFFICE_XML_EXTENSIONS
    | LEGACY_OFFICE_EXTENSIONS
    | EPUB_EXTENSIONS
    | MINERU_EXTENSIONS
    | MEDIA_EXTENSIONS
    | IMAGE_EXTENSIONS
)

# Batch still excludes audio/video binaries because ASR can be slow and should be invoked intentionally.
BATCH_SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS - MEDIA_EXTENSIONS

FORMAT_BY_EXTENSION = {
    **{ext: "pdf" for ext in PDF_EXTENSIONS},
    **{ext: "ebook" for ext in EBOOK_EXTENSIONS},
    ".docx": "docx",
    ".doc": "doc",
    ".pptx": "pptx",
    ".ppt": "ppt",
    ".xlsx": "xlsx",
    ".xls": "xls",
    **{ext: "markdown" for ext in MARKDOWN_EXTENSIONS},
    **{ext: "text" for ext in PLAIN_TEXT_EXTENSIONS | TABLE_TEXT_EXTENSIONS},
    **{ext: "html" for ext in HTML_EXTENSIONS},
    **{ext: "json" for ext in JSON_EXTENSIONS},
    **{ext: "notebook" for ext in NOTEBOOK_EXTENSIONS},
    **{ext: "subtitle_transcript" for ext in SUBTITLE_EXTENSIONS},
    **{ext: "code" for ext in CODE_EXTENSIONS},
    **{ext: "audio" for ext in AUDIO_EXTENSIONS},
    **{ext: "video" for ext in VIDEO_EXTENSIONS},
    **{ext: "image" for ext in IMAGE_EXTENSIONS},
}

SOURCE_TYPE_BY_FORMAT = {
    "pdf": "pdf_like",
    "ebook": "pdf_like",
    "docx": "pdf_like",
    "doc": "pdf_like",
    "xlsx": "pdf_like",
    "xls": "pdf_like",
    "pptx": "generic_block",
    "ppt": "generic_block",
    "markdown": "markdown_note",
    "text": "generic_block",
    "html": "generic_block",
    "json": "generic_block",
    "notebook": "generic_block",
    "subtitle_transcript": "subtitle_transcript",
    "code": "generic_block",
    "audio": "generic_block",
    "video": "generic_block",
    "image": "pdf_like",
}

SOURCE_TYPE_BY_EXTENSION = {
    ext: SOURCE_TYPE_BY_FORMAT.get(fmt, "generic_block")
    for ext, fmt in FORMAT_BY_EXTENSION.items()
}

"""逐页提取并保留字符位置；不把扫描图像假装成已读到的文本。"""
import hashlib
import io
import re
from pypdf import PdfReader
from rag.models import Chunk, Document, Page, RagError

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 200
MAX_TEXT = 1_000_000


def normalize_space(text: str) -> str:
    return " ".join(text.split())


def parse_pdf(name: str, content: bytes) -> Document:
    if not content or len(content) > MAX_BYTES:
        raise RagError("PDF 为空或超过 20 MB，请拆分后上传。")
    if not content.lstrip().startswith(b"%PDF-"):
        raise RagError("文件不是有效 PDF，请检查文件格式。")
    name = re.split(r"[/\\]", name)[-1] or "未命名.pdf"
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise RagError("暂不支持加密 PDF，请先导出未加密副本。")
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise RagError("PDF 页数应为 1–200 页，请拆分后上传。")
        pages, empty, total = [], [], 0
        for number, page in enumerate(reader.pages, 1):
            stream = page.get_contents()
            if stream is not None and len(stream.get_data()) > 5 * 1024 * 1024:
                raise RagError(f"第 {number} 页内容过大，请压缩或拆分 PDF。")
            text = normalize_space(page.extract_text() or "")
            if sum(c.isalnum() for c in text) < 20:
                empty.append(number)
                text = ""
            total += len(text)
            if total > MAX_TEXT:
                raise RagError("论文文字量超过处理上限，请拆分 PDF。")
            pages.append(Page(number, text))
        if not any(p.text for p in pages):
            raise RagError("未提取到可用文字：可能是扫描版或图片 PDF。请先 OCR，再上传带文字层的 PDF。")
        return Document(hashlib.sha256(content).hexdigest(), name, tuple(pages), tuple(empty))
    except RagError:
        raise
    except Exception as exc:
        # PDF 解析器可能抛出多种底层异常，统一为安全、可理解的提示。
        raise RagError("PDF 解析失败，文件可能损坏或字体编码不受支持，请重新导出后重试。") from exc


def split_document(document: Document, size: int = 1200, overlap: int = 200) -> list[Chunk]:
    if not 0 <= overlap < size:
        raise ValueError("切分要求 0 <= overlap < size")
    chunks = []
    for page in document.pages:
        start = 0
        while start < len(page.text):
            end = min(start + size, len(page.text))
            # 优先在空格附近断开，不改变文本，保证引用可以追溯到原页。
            if end < len(page.text):
                boundary = page.text.rfind(" ", start + size // 2, end)
                if boundary > start + overlap:
                    end = boundary
            text = page.text[start:end]
            chunks.append(Chunk(f"{document.id}:{page.number}:{start}", document.id,
                                document.name, page.number, start, end, text))
            if end == len(page.text):
                break
            start = end - overlap
    return chunks

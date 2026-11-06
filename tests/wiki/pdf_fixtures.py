"""Generated PDFs for the PDF-source tests (Aldeia-IT/aldeia-box#1483).

``make_pdf`` writes a real PDF with pypdf: a page given as text gets a
Helvetica text layer in a Flate-compressed content stream; a page given as
``None`` only draws an image (a scan-like page with no text layer).
"""

import io
import zlib

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    StreamObject,
)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _font(writer: PdfWriter):
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    return writer._add_object(font)


def _image(writer: PdfWriter):
    image = StreamObject()
    image._data = zlib.compress(b"\x80" * 16 * 16)
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(16),
            NameObject("/Height"): NumberObject(16),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/Filter"): NameObject("/FlateDecode"),
        }
    )
    return writer._add_object(image)


def text_ops(text: str) -> bytes:
    """Content-stream operators that show ``text``, one line per ``\\n``."""
    ops = ["BT", "/F1 11 Tf", "14 TL", "56 780 Td"]
    for line in text.split("\n"):
        ops.append(f"({_escape(line)}) Tj T*")
    ops.append("ET")
    return "\n".join(ops).encode("latin-1")


def make_pdf(pages: list[str | None], *, compress: bool = True) -> bytes:
    """Build a PDF whose pages carry the given text (``None`` = image only).

    :param pages: one entry per page.
    :param compress: Flate-compress the content streams (as real PDFs do).
    :returns: the PDF file bytes.
    """
    writer = PdfWriter()
    font_ref = _font(writer)
    image_ref = None
    for text in pages:
        page = writer.add_blank_page(width=595, height=842)
        resources = DictionaryObject()
        if text is None:
            image_ref = image_ref or _image(writer)
            resources[NameObject("/XObject")] = DictionaryObject(
                {NameObject("/Im0"): image_ref}
            )
            ops = b"q 400 0 0 400 96 300 cm /Im0 Do Q"
        else:
            resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font_ref})
            ops = text_ops(text)
        page[NameObject("/Resources")] = resources
        content = DecodedStreamObject()
        content.set_data(ops)
        page[NameObject("/Contents")] = writer._add_object(content)
        if compress:
            page.compress_content_streams()
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def text_is_compressed(data: bytes, text: str) -> bool:
    """Whether ``text`` sits only inside a Flate stream (not as plain bytes)."""
    return b"/FlateDecode" in data and text.encode("latin-1") not in data

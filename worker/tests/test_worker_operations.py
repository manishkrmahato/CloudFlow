import io
from PIL import Image
from app.operations import process_image


def test_compress_returns_jpeg_mime_type():
    source = io.BytesIO()
    Image.new("RGB", (15, 10), "navy").save(source, "PNG")
    result, ext, mime = process_image(source.getvalue(), {"name": "compress", "quality": 60})
    assert Image.open(io.BytesIO(result)).format == "JPEG"
    assert (ext, mime) == ("jpg", "image/jpeg")

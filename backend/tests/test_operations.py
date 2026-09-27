import io
import pytest
from PIL import Image
from app.operations import InvalidImage, process_image


def image_bytes(fmt="PNG"):
    image = Image.new("RGB", (20, 10), "red")
    output = io.BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


def test_resize_preserves_aspect_ratio():
    result, ext, mime = process_image(image_bytes(), {"name": "resize", "width": 10})
    assert Image.open(io.BytesIO(result)).size == (10, 5)
    assert (ext, mime) == ("png", "image/png")


def test_png_to_jpeg_conversion():
    result, ext, mime = process_image(image_bytes(), {"name": "png_to_jpeg"})
    assert Image.open(io.BytesIO(result)).format == "JPEG"
    assert (ext, mime) == ("jpg", "image/jpeg")


def test_grayscale():
    result, _, _ = process_image(image_bytes(), {"name": "grayscale"})
    assert Image.open(io.BytesIO(result)).mode == "L"


def test_invalid_operation_rejected():
    with pytest.raises(InvalidImage):
        process_image(image_bytes(), {"name": "bad"})

def test_rejects_oversized_pixel_dimensions(monkeypatch):
    monkeypatch.setattr("app.operations.Image.MAX_IMAGE_PIXELS", 100)
    with pytest.raises(InvalidImage, match="safely sized"):
        process_image(image_bytes(), {"name": "grayscale"})

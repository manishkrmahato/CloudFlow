import io
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
SUPPORTED = {"resize", "compress", "jpeg_to_png", "png_to_jpeg", "grayscale"}


class InvalidImage(ValueError):
    pass


def process_image(source: bytes, operation: dict) -> tuple[bytes, str, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(source))
            if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                raise InvalidImage("Image exceeds the 40 megapixel processing limit")
            image.verify()
            image = Image.open(io.BytesIO(source))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImage("The uploaded file is not a valid or safely sized image") from exc
    if image.format not in ALLOWED_FORMATS:
        raise InvalidImage("Only JPEG, PNG, and WebP images are supported")
    name = operation.get("name")
    if name not in SUPPORTED:
        raise InvalidImage("Unsupported image operation")
    output_format, options = image.format, {}
    image = ImageOps.exif_transpose(image)
    if name == "resize":
        width, height = operation.get("width"), operation.get("height")
        if not width and not height:
            raise InvalidImage("Resize requires width or height")
        if width and height:
            image.thumbnail((width, height), Image.Resampling.LANCZOS)
        elif width:
            image.thumbnail((width, max(1, round(image.height * width / image.width))), Image.Resampling.LANCZOS)
        else:
            image.thumbnail((max(1, round(image.width * height / image.height)), height), Image.Resampling.LANCZOS)
    elif name == "compress":
        image = image.convert("RGB") if image.mode not in ("RGB", "L") else image
        output_format = "JPEG"
        options = {"quality": operation.get("quality", 75), "optimize": True}
    elif name == "jpeg_to_png":
        if output_format != "JPEG":
            raise InvalidImage("JPEG to PNG requires a JPEG input")
        output_format = "PNG"
    elif name == "png_to_jpeg":
        if output_format != "PNG":
            raise InvalidImage("PNG to JPEG requires a PNG input")
        output_format = "JPEG"
    elif name == "grayscale":
        image = ImageOps.grayscale(image)
    if output_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[output_format]
    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[output_format]
    output = io.BytesIO()
    image.save(output, format=output_format, **options)
    return output.getvalue(), extension, mime




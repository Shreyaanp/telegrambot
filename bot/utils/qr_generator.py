"""QR code generation utilities."""
import io
import logging
import base64
import qrcode
from PIL import Image

logger = logging.getLogger(__name__)


def generate_qr_code(data: str, size: int = 300) -> io.BytesIO:
    """
    Generate QR code image from data.
    
    Args:
        data: The data to encode in the QR code
        size: Size of the QR code image (width and height)
        
    Returns:
        BytesIO object containing PNG image data
    """
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        bio = io.BytesIO()
        img.save(bio, "PNG")
        bio.seek(0)
        
        logger.debug(f"Generated QR code ({size}x{size}px)")
        return bio
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise


def decode_base64_qr(base64_qr: str) -> str:
    """
    Decode base64-encoded QR data from Mercle SDK.
    
    Args:
        base64_qr: Base64-encoded QR data
        
    Returns:
        Decoded string data
    """
    try:
        decoded_bytes = base64.b64decode(base64_qr)
        decoded_str = decoded_bytes.decode("utf-8")
        return decoded_str
    except Exception as e:
        logger.error(f"Failed to decode base64 QR data: {e}")
        raise


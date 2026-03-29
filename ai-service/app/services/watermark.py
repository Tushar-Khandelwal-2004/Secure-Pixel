import cv2
import traceback
from imwatermark import WatermarkEncoder, WatermarkDecoder

def encode_watermark(image_path: str, secret_data: str, output_path: str):
    try:
        bgr = cv2.imread(image_path)
        if bgr is None:
            return
            
        encoder = WatermarkEncoder()
        watermark_bytes = secret_data.encode('utf-8')
        encoder.set_watermark('bytes', watermark_bytes)
        
        # Switched to dwtDctSvd for extreme stability
        bgr_encoded = encoder.encode(bgr, 'dwtDctSvd') 
        
        cv2.imwrite(output_path, bgr_encoded)
    except Exception as e:
        print(f"ENCODE FAILED: {str(e)}")

def decode_watermark(image_path: str, payload_length: int = 4) -> str:
    try:
        bgr = cv2.imread(image_path)
        if bgr is None:
            return None
            
        decoder = WatermarkDecoder('bytes', payload_length * 8)
        
        # Switched to dwtDctSvd to match encoder
        watermark_bytes = decoder.decode(bgr, 'dwtDctSvd') 
        
        decoded_text = watermark_bytes.decode('utf-8', errors='ignore').strip('\x00')
        return decoded_text
    except Exception as e:
        print(f"DECODE FAILED: {str(e)}")
        return None
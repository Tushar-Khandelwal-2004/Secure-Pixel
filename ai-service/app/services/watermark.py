from PIL import Image

def encode_lsb(image_path: str, secret_data: str, output_path: str):
    img = Image.open(image_path).convert('RGB')
    secret_data += "====END===="
    binary_data = ''.join(format(ord(char), '08b') for char in secret_data)
    
    pixels = img.load()
    width, height = img.size
    data_idx = 0
    data_len = len(binary_data)
    
    for y in range(height):
        for x in range(width):
            if data_idx < data_len:
                r, g, b = pixels[x, y]
                if data_idx < data_len:
                    r = (r & 254) | int(binary_data[data_idx])
                    data_idx += 1
                if data_idx < data_len:
                    g = (g & 254) | int(binary_data[data_idx])
                    data_idx += 1
                if data_idx < data_len:
                    b = (b & 254) | int(binary_data[data_idx])
                    data_idx += 1
                pixels[x, y] = (r, g, b)
            else:
                break
        if data_idx >= data_len:
            break
            
    img.save(output_path, "PNG")

def decode_lsb(image_path: str) -> str:
    try:
        img = Image.open(image_path).convert('RGB')
        pixels = img.load()
        width, height = img.size
        
        binary_data = ""
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                binary_data += str(r & 1)
                binary_data += str(g & 1)
                binary_data += str(b & 1)
                
        decoded_text = ""
        for i in range(0, len(binary_data), 8):
            byte = binary_data[i:i+8]
            if len(byte) < 8:
                break
            decoded_text += chr(int(byte, 2))
            
            if "====END====" in decoded_text:
                return decoded_text.split("====END====")[0]
                
        return None
    except Exception:
        return None
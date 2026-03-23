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
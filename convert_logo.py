from PIL import Image
import os

def make_transparent(input_path, output_path):
    img = Image.open(input_path)
    img = img.convert("RGBA")
    
    datas = img.getdata()
    
    new_data = []
    for item in datas:
        # If pixels are white (or very close to white), make them transparent
        if item[0] > 240 and item[1] > 240 and item[2] > 240:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
            
    img.putdata(new_data)
    img.save(output_path, "PNG")

if __name__ == "__main__":
    input_file = r"c:\Users\bradl\Desktop\healthcare_ai_agent\web\brain_provided.jpg"
    output_file = r"c:\Users\bradl\Desktop\healthcare_ai_agent\web\brain_transparent.png"
    
    if os.path.exists(input_file):
        make_transparent(input_file, output_file)
        print(f"Successfully converted {input_file} to {output_file}")
    else:
        print(f"Input file not found: {input_file}")

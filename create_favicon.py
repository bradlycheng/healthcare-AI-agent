from PIL import Image
import os

def create_favicon(input_path, output_path):
    img = Image.open(input_path)
    # Ensure it stays RGBA for transparency
    img = img.convert("RGBA")
    # Resize to standard favicon size
    img = img.resize((32, 32), Image.Resampling.LANCZOS)
    img.save(output_path, "PNG")

if __name__ == "__main__":
    input_file = r"c:\Users\bradl\Desktop\healthcare_ai_agent\web\brain_transparent.png"
    output_file = r"c:\Users\bradl\Desktop\healthcare_ai_agent\web\favicon.png"
    
    if os.path.exists(input_file):
        create_favicon(input_file, output_file)
        print(f"Successfully created favicon at {output_file}")
    else:
        print(f"Input file not found: {input_file}")

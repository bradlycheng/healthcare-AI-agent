from PIL import Image, ImageDraw, ImageFont
import os

def create_icons():
    web_dir = r"c:\Users\bradl\Desktop\healthcare_ai_agent\web"
    logo_path = os.path.join(web_dir, "brain_transparent.png")
    
    if not os.path.exists(logo_path):
        print(f"Error: {logo_path} not found")
        return

    # 1. Apple Touch Icon (180x180) - Square with branding
    apple_path = os.path.join(web_dir, "apple-touch-icon.png")
    with Image.open(logo_path) as img:
        # Apple icons are usually square and often look better with a slight padding
        # But we'll just resize the logo centered on a dark background or transparent
        apple_icon = Image.new("RGBA", (180, 180), (5, 5, 17, 255)) # Match site bg-dark
        
        # Resize logo to fit nicely
        logo_aspect = img.width / img.height
        new_h = 140
        new_w = int(new_h * logo_aspect)
        logo_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Paste centered
        x = (180 - new_w) // 2
        y = (180 - new_h) // 2
        apple_icon.paste(logo_resized, (x, y), logo_resized)
        apple_icon.save(apple_path, "PNG")
        print(f"Created {apple_path}")

    # 2. OG Image (1200x630) - Social sharing
    og_path = os.path.join(web_dir, "og-image.png")
    og_img = Image.new("RGB", (1200, 630), (5, 5, 17)) # Match site bg-dark
    
    with Image.open(logo_path) as img:
        # Resize logo for OG Image
        logo_h = 300
        logo_w = int(logo_h * (img.width / img.height))
        logo_resized = img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
        
        # Draw logo centered
        x = (1200 - logo_w) // 2
        y = (630 - logo_h) // 2 - 50 # Slightly above center
        og_img.paste(logo_resized, (x, y), logo_resized)
        
        draw = ImageDraw.Draw(og_img)
        # We can't easily rely on finding a specific font, so we'll try a default or just use the logo
        # For professional look, having "Health Data Agent" text below it is good.
        # If we can't find a font, we'll skip the text or use a basic one.
        print("Icons generated successfully.")
    
    og_img.save(og_path, "PNG")
    print(f"Created {og_path}")

if __name__ == "__main__":
    create_icons()

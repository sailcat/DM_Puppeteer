"""
Generate test character PNGs for trying out DM Puppeteer.
Run this once to create sample sprites, then replace with your real art.

Usage: python create_test_characters.py
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Needs Pillow: pip install Pillow")
    sys.exit(1)

# Put them in the data/characters dir that DM Puppeteer uses
BASE_DIR = Path(__file__).parent / "data" / "characters"


def make_character(char_id, name, color, size=(400, 400)):
    folder = BASE_DIR / char_id
    folder.mkdir(parents=True, exist_ok=True)

    frames = {
        "idle":       (False, True),   # (mouth_open, eyes_open)
        "blink":      (False, False),
        "talk":       (True,  True),
        "talk_blink": (True,  False),
    }

    for frame_name, (mouth, eyes) in frames.items():
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy = size[0] // 2, size[1] // 2

        # Head
        draw.ellipse([cx-150, cy-150, cx+150, cy+150],
                     fill=color, outline=(0, 0, 0), width=3)

        # Eyes
        for ex in [cx-50, cx+50]:
            if eyes:
                draw.ellipse([ex-15, cy-60, ex+15, cy-20],
                             fill="white", outline="black", width=2)
                draw.ellipse([ex-7, cy-50, ex+7, cy-30], fill="black")
            else:
                draw.line([ex-15, cy-40, ex+15, cy-40], fill="black", width=3)

        # Mouth
        if mouth:
            draw.ellipse([cx-30, cy+30, cx+30, cy+70],
                         fill=(80, 0, 0), outline="black", width=2)
        else:
            draw.arc([cx-25, cy+35, cx+25, cy+55], 0, 180, fill="black", width=3)

        # Name
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except OSError:
            font = ImageFont.load_default()
        draw.text((cx, cy + 120), name, fill="black", anchor="mm", font=font)

        img.save(folder / f"{frame_name}.png")
        print(f"  {folder / frame_name}.png")


if __name__ == "__main__":
    print("Creating test characters...\n")
    make_character("test_gatrina", "Gatrina",  (180, 120, 200, 255))
    make_character("test_elnar",   "Elnar",    (120, 180, 140, 255))
    make_character("test_olivia",  "Olivia",   (200, 160, 120, 255))
    print("\nDone! Now run: python run.py")
    print("The characters will appear automatically in the library.")

    # Also create a simple state.json so the app picks them up
    import json
    state_path = Path(__file__).parent / "data" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    chars = [
        {"id": "test_gatrina", "name": "Gatrina", "folder": str(BASE_DIR / "test_gatrina")},
        {"id": "test_elnar",   "name": "Elnar",   "folder": str(BASE_DIR / "test_elnar")},
        {"id": "test_olivia",  "name": "Olivia",  "folder": str(BASE_DIR / "test_olivia")},
    ]

    state = {
        "characters": chars,
        "deck_assignments": {"0": "test_gatrina", "1": "test_elnar", "2": "test_olivia"},
        "hotkey_assignments": {},
        "active_character_id": None,
        "mic_threshold": 0.02,
        "mic_device": None,
        "deck_mode": "direct",
        "deck_brightness": 80,
        "overlay_width": 400,
        "overlay_height": 400,
        "overlay_x": 100,
        "overlay_y": 100,
    }

    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)

    print(f"\nWrote {state_path}")

# Icon Creation Instructions

For the unRAID Community Applications template, you'll need to create an icon file.

## Requirements:
- **Format**: PNG
- **Size**: 128x128 pixels
- **Background**: Transparent or solid color
- **Style**: Should match unRAID's design aesthetic

## Suggested Icon Design:
- A hard drive or storage icon
- Simple, clean design
- Use the primary color from your theme (orange for unRAID theme)
- Include text "SA" or "Storage" if desired

## Steps to Create:
1. Use any image editor (GIMP, Photoshop, or online tools)
2. Create a 128x128 pixel canvas
3. Design your icon
4. Export as PNG
5. Save as `icon.png` in the root directory

## Alternative:
You can use a simple text-based icon or find a suitable free icon from:
- [Feather Icons](https://feathericons.com/)
- [Heroicons](https://heroicons.com/)
- [Material Icons](https://material.io/icons/)

## Example Command (using ImageMagick):
```bash
convert -size 128x128 xc:transparent -fill "#f37920" -draw "circle 64,64 64,20" icon.png
```

This will create a simple circular icon in the unRAID orange color.

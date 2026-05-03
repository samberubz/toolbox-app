"""
Toolbox App
A multi-tool Streamlit application for image and file operations.

Tools:
    1. HEIC -> JPG/PNG converter (max quality, batch supported)
    2. iMessage Creator — composes bubbles using:
         - A solid rounded rectangle for the body (any size)
         - The exact tail piece extracted from the user's reference template
       Result: pixel-perfect tail at any bubble size, no distortion.
"""

import io
import os
from pathlib import Path
from typing import List, Tuple

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# Register HEIF/HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False


# --------------------------------------------------------------------------- #
# Page configuration
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Toolbox",
    page_icon="🧰",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# --------------------------------------------------------------------------- #
# Paths & assets
# --------------------------------------------------------------------------- #
APP_DIR = Path(__file__).parent
FONT_DIR = APP_DIR / "fonts"
ASSET_DIR = APP_DIR / "assets"

# Tail-corner pieces (bottom-outer corner WITH the tail bump),
# extracted directly from the user-provided template.
TAIL_BLUE = ASSET_DIR / "blue_tail_corner.png"
TAIL_GRAY = ASSET_DIR / "gray_tail_corner.png"
TYPING_TEMPLATE = ASSET_DIR / "bubble_typing.png"

# Solid fill colors sampled from the user's template
FILL_BLUE = (0, 137, 254)
FILL_GRAY = (233, 232, 238)

# Native source-template proportions (used for tail scaling)
# In the source 300×62 template, the bubble body is ~50px tall.
SOURCE_BODY_HEIGHT = 50


# --------------------------------------------------------------------------- #
# Font handling
# --------------------------------------------------------------------------- #
def _find_font(filenames: List[str]) -> str | None:
    for name in filenames:
        candidate = FONT_DIR / name
        if candidate.exists():
            return str(candidate)
    system_dirs = [
        "/usr/share/fonts", "/usr/local/share/fonts",
        "/Library/Fonts", "/System/Library/Fonts",
        os.path.expanduser("~/.fonts"), os.path.expanduser("~/Library/Fonts"),
    ]
    for base in system_dirs:
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for f in files:
                if f in filenames:
                    return os.path.join(root, f)
    return None


def get_imessage_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "SF-Pro-Text-Regular.otf", "SFProText-Regular.otf",
        "SFProDisplay-Regular.otf",
        "Inter-Regular.ttf", "Inter-Regular.otf",
        "DejaVuSans.ttf",
    ]
    font_path = _find_font(candidates)
    if font_path is None:
        return ImageFont.load_default()
    return ImageFont.truetype(font_path, size)


# --------------------------------------------------------------------------- #
# Tool 1: HEIC Converter
# --------------------------------------------------------------------------- #
def heic_converter_tab() -> None:
    st.header("HEIC Converter")
    st.caption(
        "Convert HEIC / HEIF photos to JPG or PNG at maximum quality. "
        "Drop multiple files to convert them all at once."
    )

    if not HEIC_SUPPORT:
        st.error(
            "HEIC support is not installed. Add `pillow-heif` to requirements.txt."
        )
        return

    uploaded_files = st.file_uploader(
        "Drop one or more HEIC files (batch supported)",
        type=["heic", "heif"],
        accept_multiple_files=True,
        key="heic_uploader",
    )

    output_format = st.radio(
        "Output format",
        options=["JPG", "PNG"],
        horizontal=True,
        help="JPG = smaller file, near-lossless at quality 100. "
             "PNG = fully lossless, larger file.",
    )

    if not uploaded_files:
        st.info("Upload one or more HEIC files above to begin.")
        return

    st.write(f"**{len(uploaded_files)} file(s) ready to convert.**")

    if st.button("Convert all", type="primary", use_container_width=True):
        progress = st.progress(0.0)
        status = st.empty()
        results: List[Tuple[str, bytes, str]] = []

        for i, up in enumerate(uploaded_files, start=1):
            status.write(f"Converting {up.name} ({i}/{len(uploaded_files)})…")
            try:
                image = Image.open(up)
                exif_bytes = image.info.get("exif", b"")
                buf = io.BytesIO()
                stem = Path(up.name).stem

                if output_format == "JPG":
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    image.save(
                        buf, format="JPEG", quality=100, subsampling=0,
                        optimize=True, exif=exif_bytes,
                    )
                    out_name = f"{stem}.jpg"
                    mime = "image/jpeg"
                else:
                    image.save(buf, format="PNG", compress_level=6, optimize=True)
                    out_name = f"{stem}.png"
                    mime = "image/png"

                results.append((out_name, buf.getvalue(), mime))
            except Exception as e:
                st.error(f"Failed to convert {up.name}: {e}")

            progress.progress(i / len(uploaded_files))

        progress.empty()
        status.empty()

        if results:
            st.success(f"Converted {len(results)} file(s).")

            if len(results) > 1:
                import zipfile
                zbuf = io.BytesIO()
                with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, data, _ in results:
                        zf.writestr(name, data)
                st.download_button(
                    label=f"⬇️  Download all {len(results)} files as ZIP",
                    data=zbuf.getvalue(),
                    file_name="converted.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                )
                st.caption("Or download files individually:")

            for name, data, mime in results:
                st.download_button(
                    label=f"⬇️  {name}",
                    data=data,
                    file_name=name,
                    mime=mime,
                    key=f"dl_{name}",
                    use_container_width=True,
                )


# --------------------------------------------------------------------------- #
# Tool 2: iMessage Creator
# --------------------------------------------------------------------------- #

def _wrap_text_to_width(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> List[str]:
    lines: List[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for w in words:
            trial = (current + " " + w).strip() if current else w
            bbox = draw.textbbox((0, 0), trial, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = w
        if current:
            lines.append(current)
    return lines


def render_text_bubble(
    text: str,
    *,
    side: str,                    # "right" (blue/sent) or "left" (gray/received)
    font_size: int = 64,
    show_delivered: bool = True,
    max_text_width_px: int | None = None,
) -> Image.Image:
    """
    Render an iMessage bubble:
      1. Draw a solid-color rounded rectangle for the body
      2. Composite the actual tail piece (extracted from the user's template)
         on top of the bottom-outer corner
      3. Overlay text inside the body
    Returns RGBA image with transparent background, tightly cropped.
    """
    is_blue = (side == "right")
    fill_color = FILL_BLUE if is_blue else FILL_GRAY
    text_color = (255, 255, 255) if is_blue else (0, 0, 0)
    delivered_color = (142, 142, 147)
    tail_path = TAIL_BLUE if is_blue else TAIL_GRAY

    font = get_imessage_font(font_size)
    delivered_font = get_imessage_font(max(12, int(font_size * 0.42)))

    # ---- Layout — proportional to font ----
    pad_x = int(font_size * 0.55)
    pad_y = int(font_size * 0.32)
    line_spacing = int(font_size * 0.18)
    # Corner radius: matches iOS proportions (~1× font for small bubbles)
    corner_radius = int(font_size * 0.95)

    if max_text_width_px is None:
        max_text_width_px = int(font_size * 14)

    # ---- Measure text ----
    scratch = Image.new("RGBA", (1, 1))
    sdraw = ImageDraw.Draw(scratch)
    lines = _wrap_text_to_width(text, font, max_text_width_px, sdraw)
    if not lines:
        lines = [""]

    line_widths = []
    for ln in lines:
        bbox = sdraw.textbbox((0, 0), ln if ln else " ", font=font)
        line_widths.append(bbox[2] - bbox[0])
    text_w = max(line_widths) if line_widths else 0

    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    text_h = line_h * len(lines) + line_spacing * (len(lines) - 1)

    # ---- Body dimensions ----
    body_w = text_w + 2 * pad_x
    body_h = text_h + 2 * pad_y
    # Cap corner radius to half the smallest dimension (so short bubbles
    # become full pills like real iMessage)
    corner_radius = min(corner_radius, body_h // 2, body_w // 2)

    # ---- Load and scale the tail piece ----
    tail_src = Image.open(tail_path).convert("RGBA")
    # Scale the tail to match the bubble proportions: in the source, the
    # bubble body is 50px tall; we scale the tail by (body_h / 50) so it
    # matches. Using the body height as the reference keeps the tail
    # proportional for short bubbles. For very tall multi-line bubbles
    # the tail in real iMessage doesn't grow much — we cap the scale.
    raw_scale = body_h / SOURCE_BODY_HEIGHT
    # Cap the scale at a reasonable maximum so the tail doesn't get
    # absurdly big on very tall bubbles. Real iMessage tails stay roughly
    # constant relative to the corner radius.
    scale = min(raw_scale, font_size / 25.0)  # tail roughly = font_size in size
    scale = max(scale, 0.5)  # don't let it shrink too much either
    new_w = max(8, int(tail_src.size[0] * scale))
    new_h = max(8, int(tail_src.size[1] * scale))
    tail = tail_src.resize((new_w, new_h), Image.LANCZOS)

    # ---- Canvas: body + room for tail bump below + room for "Delivered" ----
    delivered_h = 0
    if is_blue and show_delivered:
        dbbox = sdraw.textbbox((0, 0), "Delivered", font=delivered_font)
        delivered_h = (dbbox[3] - dbbox[1]) + int(font_size * 0.30)

    # The tail piece is wider than just the corner — it includes the tail
    # bump that extends DOWN past body_h. The piece's height (after
    # scaling) is tail.size[1]; the part that overlays the bubble's
    # bottom-outer corner takes the upper portion, and the tail bump
    # extends below body_h.
    # For the source piece (70×27), body portion ≈ rows 0-15 (overlaps
    # corner of bubble), tail bump extends rows 15-27 below body.
    # After scaling, the bump extends new_h - int(15*scale) below body_h.
    tail_overhang = max(0, new_h - int(15 * scale))

    canvas_w = body_w
    canvas_h = body_h + tail_overhang + delivered_h
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # ---- Step 1: body as rounded rectangle ----
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [(0, 0), (body_w - 1, body_h - 1)],
        radius=corner_radius,
        fill=fill_color + (255,),
    )

    # ---- Step 2: composite the tail piece over the bottom-outer corner ----
    if is_blue:
        # Bottom-RIGHT corner. Position the tail piece so its right edge
        # aligns with the bubble's right edge, and its top is positioned
        # so the corner part of the piece OVERLAPS the bubble's bottom-
        # right rounded corner.
        # The piece's "body part" (the rounded corner curve) sits in the
        # top portion of the piece. We want that to land on the bubble's
        # rounded corner. So:
        tail_x = body_w - new_w
        # Tail's rounded corner spans the upper ~int(15*scale) px.
        # We want it to sit on the bubble's bottom-right rounded corner,
        # which spans roughly y = body_h - corner_radius .. body_h.
        # Align so the BOTTOM of the tail's corner-overlap region is at
        # body_h:
        tail_y = body_h - int(15 * scale)
    else:
        # Bottom-LEFT corner
        tail_x = 0
        tail_y = body_h - int(15 * scale)

    canvas.alpha_composite(tail, (tail_x, tail_y))

    # ---- Step 3: text inside body ----
    text_y = (body_h - text_h) // 2
    text_x = pad_x
    cur_y = text_y
    for ln in lines:
        draw.text((text_x, cur_y), ln, font=font, fill=text_color + (255,))
        cur_y += line_h + line_spacing

    # ---- Step 4: "Delivered" — only on blue ----
    if is_blue and show_delivered:
        dtext = "Delivered"
        dbbox = draw.textbbox((0, 0), dtext, font=delivered_font)
        dw = dbbox[2] - dbbox[0]
        dx = body_w - dw - 4
        dy = body_h + tail_overhang + int(font_size * 0.05)
        draw.text((dx, dy), dtext, font=delivered_font,
                  fill=delivered_color + (255,))

    # ---- Tight crop ----
    alpha = canvas.split()[3]
    bbox = alpha.getbbox()
    if bbox:
        safety = 2
        w, h = canvas.size
        canvas = canvas.crop((
            max(0, bbox[0] - safety),
            max(0, bbox[1] - safety),
            min(w, bbox[2] + safety),
            min(h, bbox[3] + safety),
        ))

    return canvas


def render_typing_bubble(scale: float = 1.0) -> Image.Image:
    img = Image.open(TYPING_TEMPLATE).convert("RGBA")
    if scale != 1.0:
        new_size = (max(1, int(img.size[0] * scale)),
                    max(1, int(img.size[1] * scale)))
        img = img.resize(new_size, Image.LANCZOS)
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img


def _make_checkered_preview(img: Image.Image, square: int = 12) -> Image.Image:
    w, h = img.size
    bg = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(bg)
    light = (235, 235, 235, 255)
    for y in range(0, h, square):
        for x in range(0, w, square):
            if ((x // square) + (y // square)) % 2 == 0:
                draw.rectangle(
                    [(x, y), (x + square - 1, y + square - 1)],
                    fill=light,
                )
    bg.alpha_composite(img)
    return bg


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
def imessage_creator_tab() -> None:
    st.header("iMessage Creator")
    st.caption(
        "Generate a single iMessage element on a transparent background, "
        "then download and paste it on any photo."
    )

    needed = [TAIL_BLUE, TAIL_GRAY, TYPING_TEMPLATE]
    missing = [p.name for p in needed if not p.exists()]
    if missing:
        st.error(
            f"Missing template files in `assets/`: {', '.join(missing)}. "
            "Make sure the `assets/` folder is in your repo."
        )
        return

    bubble_type = st.radio(
        "Type",
        options=["Sent (blue)", "Reply (gray)", "Typing… (3 dots)"],
        horizontal=True,
    )

    bubble: Image.Image | None = None
    download_filename = "imessage_bubble.png"

    if bubble_type == "Typing… (3 dots)":
        scale = st.slider(
            "Size scale",
            min_value=0.5, max_value=4.0, value=1.5, step=0.1,
        )
        bubble = render_typing_bubble(scale=scale)
        download_filename = "imessage_typing.png"
    else:
        side = "right" if bubble_type.startswith("Sent") else "left"
        font_size = st.slider(
            "Font size (px)",
            min_value=24, max_value=160, value=64,
        )
        default_text = (
            "Can I call you back later? I'm at an appointment."
            if side == "right" else "You know it!"
        )
        text = st.text_area(
            "Message",
            value=default_text,
            height=80,
            max_chars=500,
        )
        if not text.strip():
            st.info("Type a message above.")
            return

        bubble = render_text_bubble(
            text=text,
            side=side,
            font_size=font_size,
            show_delivered=(side == "right"),
        )
        download_filename = (
            "imessage_sent.png" if side == "right" else "imessage_reply.png"
        )

    st.divider()
    st.markdown(
        "**Preview** — checkered background shows transparency "
        "(it won't appear when you paste it on a photo)."
    )
    preview = _make_checkered_preview(bubble)
    st.image(preview, use_container_width=False)
    st.caption(
        f"PNG size: {bubble.size[0]} × {bubble.size[1]}px · "
        "Background fully transparent."
    )

    buf = io.BytesIO()
    bubble.save(buf, format="PNG", optimize=True)
    st.download_button(
        label="⬇️  Download PNG (transparent)",
        data=buf.getvalue(),
        file_name=download_filename,
        mime="image/png",
        type="primary",
        use_container_width=True,
    )

    with st.expander("How to use this on a photo"):
        st.markdown(
            "1. Click **Download PNG** above.\n"
            "2. Open your photo in any editor: **Photos** (iPhone/Mac), "
            "**Photoshop**, **Canva**, **Pixelmator**, **GIMP**, etc.\n"
            "3. Insert / drag the downloaded PNG onto your photo.\n"
            "4. Resize and position freely — transparent background means "
            "only the bubble shows.\n\n"
            "*iPhone tip: open the PNG in Photos → Share → Copy Photo "
            "→ open your target photo in Markup → paste.*"
        )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("🧰 Toolbox")
    st.caption("A small collection of file & image utilities.")

    tab1, tab2 = st.tabs(["HEIC → JPG/PNG", "iMessage Creator"])
    with tab1:
        heic_converter_tab()
    with tab2:
        imessage_creator_tab()


if __name__ == "__main__":
    main()

"""
Toolbox App
A multi-tool Streamlit application for image and file operations.

Tools:
    1. HEIC -> JPG/PNG converter (max quality, batch supported)
    2. iMessage Creator — generate a single iMessage bubble (sent or received)
       on a transparent background, ready to paste onto any photo.
"""

import io
import os
from pathlib import Path
from typing import List, Tuple

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# Register HEIF/HEIC support with Pillow
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
# Font handling
# --------------------------------------------------------------------------- #
FONT_DIR = Path(__file__).parent / "fonts"


def _find_font(filenames: List[str]) -> str | None:
    """Return the first font file that exists from a list of candidates."""
    for name in filenames:
        candidate = FONT_DIR / name
        if candidate.exists():
            return str(candidate)
    system_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/Library/Fonts",
        "/System/Library/Fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/Library/Fonts"),
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
    """Load the closest-to-SF-Pro font available."""
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
# Tool 1: HEIC Converter (batch)
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
                        buf,
                        format="JPEG",
                        quality=100,
                        subsampling=0,
                        optimize=True,
                        exif=exif_bytes,
                    )
                    out_name = f"{stem}.jpg"
                    mime = "image/jpeg"
                else:
                    image.save(
                        buf,
                        format="PNG",
                        compress_level=6,
                        optimize=True,
                    )
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

            # ZIP download — most convenient for batch
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

# Authentic iMessage colors (sampled from iOS)
IMSG_BLUE_TOP = (10, 132, 255)
IMSG_BLUE_BOTTOM = (0, 122, 255)
IMSG_GRAY = (229, 229, 234)
IMSG_TEXT_DARK = (0, 0, 0)
IMSG_TEXT_LIGHT = (255, 255, 255)
IMSG_DELIVERED_GRAY = (142, 142, 147)


def _wrap_text_to_width(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> List[str]:
    """Wrap text so each line fits within max_width pixels."""
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


def render_single_bubble(
    text: str,
    *,
    side: str,                          # "right" (blue/sent) or "left" (gray/received)
    font_size: int = 64,
    max_text_width_px: int = 900,
    show_delivered: bool = True,        # ignored for "left"
) -> Image.Image:
    """
    Render a single iMessage bubble on a transparent background.
    Returns a tightly-cropped RGBA Image with full transparency outside
    the bubble — ready to paste on any photo and rescale freely.
    """
    # ---- Geometry — all proportional to font size -------------------------
    pad_x = int(font_size * 0.55)
    pad_y = int(font_size * 0.35)
    line_spacing = int(font_size * 0.18)
    tail_size = int(font_size * 0.40)

    # ---- Measure text first to figure out canvas size ---------------------
    font = get_imessage_font(font_size)
    delivered_font = get_imessage_font(max(12, int(font_size * 0.42)))

    # We need a draw context to measure — use a tiny scratch image
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

    bubble_w = text_w + 2 * pad_x
    bubble_h = text_h + 2 * pad_y
    corner_radius = min(bubble_h // 2, bubble_w // 2)

    # ---- Compute canvas size with breathing room for tail + delivered ----
    # The tail pokes out on the side, so we need extra width.
    tail_pad = int(tail_size * 1.4)  # accommodates lobe + knob
    margin = max(2, int(font_size * 0.10))

    delivered_h = 0
    delivered_w_estimate = 0
    if side == "right" and show_delivered:
        dbbox = sdraw.textbbox((0, 0), "Delivered", font=delivered_font)
        d_text_w = dbbox[2] - dbbox[0]
        d_text_h = dbbox[3] - dbbox[1]
        delivered_h = d_text_h + int(font_size * 0.30)
        delivered_w_estimate = d_text_w  # we right-align under the bubble

    canvas_w = bubble_w + tail_pad + 2 * margin
    canvas_h = bubble_h + delivered_h + 2 * margin

    # ---- Place bubble on the canvas --------------------------------------
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if side == "right":
        # Bubble on the left side of the canvas; tail pokes right
        bubble_x1 = margin
    else:
        # Bubble on the right side of the canvas; tail pokes left
        bubble_x1 = margin + tail_pad
    bubble_y1 = margin
    bubble_x2 = bubble_x1 + bubble_w
    bubble_y2 = bubble_y1 + bubble_h

    # ---- Bubble fill ------------------------------------------------------
    if side == "right":
        # Blue gradient
        grad = Image.new("RGBA", (bubble_w, bubble_h), IMSG_BLUE_BOTTOM + (255,))
        gd = ImageDraw.Draw(grad)
        for y in range(bubble_h):
            t = y / max(1, bubble_h - 1)
            r = int(IMSG_BLUE_TOP[0] * (1 - t) + IMSG_BLUE_BOTTOM[0] * t)
            g = int(IMSG_BLUE_TOP[1] * (1 - t) + IMSG_BLUE_BOTTOM[1] * t)
            b = int(IMSG_BLUE_TOP[2] * (1 - t) + IMSG_BLUE_BOTTOM[2] * t)
            gd.line([(0, y), (bubble_w, y)], fill=(r, g, b, 255))
        mask = Image.new("L", (bubble_w, bubble_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [(0, 0), (bubble_w - 1, bubble_h - 1)],
            radius=corner_radius,
            fill=255,
        )
        img.paste(grad, (bubble_x1, bubble_y1), mask)
        text_color = IMSG_TEXT_LIGHT
    else:
        draw.rounded_rectangle(
            [(bubble_x1, bubble_y1), (bubble_x2, bubble_y2)],
            radius=corner_radius,
            fill=IMSG_GRAY + (255,),
        )
        text_color = IMSG_TEXT_DARK

    # ---- Tail (lobe + detached knob) --------------------------------------
    tail_color = IMSG_BLUE_BOTTOM if side == "right" else IMSG_GRAY
    lobe_w = int(tail_size * 1.4)
    lobe_h = int(tail_size * 1.6)
    knob_r = max(2, int(tail_size * 0.32))

    if side == "right":
        lobe_cx = bubble_x2 + int(tail_size * 0.2)
        lobe_cy = bubble_y2 - int(lobe_h * 0.45)
        draw.ellipse(
            [(lobe_cx - lobe_w // 2, lobe_cy - lobe_h // 2),
             (lobe_cx + lobe_w // 2, lobe_cy + lobe_h // 2)],
            fill=tail_color + (255,),
        )
        knob_cx = bubble_x2 + int(tail_size * 0.95)
        knob_cy = bubble_y2 - knob_r // 2
        draw.ellipse(
            [(knob_cx - knob_r, knob_cy - knob_r),
             (knob_cx + knob_r, knob_cy + knob_r)],
            fill=tail_color + (255,),
        )
    else:
        lobe_cx = bubble_x1 - int(tail_size * 0.2)
        lobe_cy = bubble_y2 - int(lobe_h * 0.45)
        draw.ellipse(
            [(lobe_cx - lobe_w // 2, lobe_cy - lobe_h // 2),
             (lobe_cx + lobe_w // 2, lobe_cy + lobe_h // 2)],
            fill=tail_color + (255,),
        )
        knob_cx = bubble_x1 - int(tail_size * 0.95)
        knob_cy = bubble_y2 - knob_r // 2
        draw.ellipse(
            [(knob_cx - knob_r, knob_cy - knob_r),
             (knob_cx + knob_r, knob_cy + knob_r)],
            fill=tail_color + (255,),
        )

    # ---- Text -------------------------------------------------------------
    ty = bubble_y1 + pad_y
    for ln in lines:
        tx = bubble_x1 + pad_x
        draw.text((tx, ty), ln, font=font, fill=text_color + (255,))
        ty += line_h + line_spacing

    # ---- "Delivered" — only for blue/sent bubbles -------------------------
    if side == "right" and show_delivered:
        dtext = "Delivered"
        dbbox = draw.textbbox((0, 0), dtext, font=delivered_font)
        dw = dbbox[2] - dbbox[0]
        # Right-align under the bubble's right edge (matches iMessage)
        dx = bubble_x2 - dw
        dy = bubble_y2 + int(font_size * 0.25)
        draw.text((dx, dy), dtext, font=delivered_font,
                  fill=IMSG_DELIVERED_GRAY + (255,))

    # ---- Tight crop — remove all transparent margins ----------------------
    # Get the alpha channel and find the bbox of non-transparent pixels.
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox:
        # Add a tiny safety margin so anti-aliased edges aren't clipped
        safety = 2
        x0 = max(0, bbox[0] - safety)
        y0 = max(0, bbox[1] - safety)
        x1 = min(canvas_w, bbox[2] + safety)
        y1 = min(canvas_h, bbox[3] + safety)
        img = img.crop((x0, y0, x1, y1))

    return img


def imessage_creator_tab() -> None:
    st.header("iMessage Creator")
    st.caption(
        "Generate a single iMessage bubble on a transparent background. "
        "Download as PNG, then paste it on any photo and rescale freely "
        "in your editor (Photos, Photoshop, Canva, etc.)."
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        side_label = st.radio(
            "Bubble style",
            options=["Sent (blue)", "Reply (gray)"],
            horizontal=True,
            help="Sent bubbles include 'Delivered' underneath. "
                 "Reply bubbles do not (matches iMessage).",
        )
    with col2:
        font_size = st.slider(
            "Resolution (font size in px)",
            min_value=32, max_value=160, value=72,
            help="Higher = larger PNG, sharper when scaled. "
                 "Doesn't affect final size — you'll resize on your photo anyway.",
        )

    side = "right" if side_label.startswith("Sent") else "left"

    text = st.text_area(
        "Message",
        value="Can I call you back later? I'm at an appointment.",
        height=80,
        max_chars=500,
    )

    if not text.strip():
        st.info("Type a message above to generate the bubble.")
        return

    # Render
    bubble = render_single_bubble(
        text=text,
        side=side,
        font_size=font_size,
        show_delivered=(side == "right"),
    )

    st.divider()
    st.markdown("**Preview** (transparent background — checkered pattern shows transparency)")

    # Build a checkered preview background so transparency is visible
    preview = _make_checkered_preview(bubble)
    st.image(preview, use_container_width=False)

    st.caption(
        f"PNG size: {bubble.size[0]} × {bubble.size[1]}px · "
        "Background is fully transparent."
    )

    # Download
    buf = io.BytesIO()
    bubble.save(buf, format="PNG", optimize=True)
    st.download_button(
        label="⬇️  Download bubble (PNG, transparent)",
        data=buf.getvalue(),
        file_name="imessage_bubble.png",
        mime="image/png",
        type="primary",
        use_container_width=True,
    )

    with st.expander("How to use this on a photo"):
        st.markdown(
            "1. Click **Download bubble (PNG)** above.\n"
            "2. Open your photo in any editor: **Photos** (iPhone/Mac), "
            "**Photoshop**, **Canva**, **Pixelmator**, **GIMP**, etc.\n"
            "3. Insert / drag the downloaded PNG onto your photo.\n"
            "4. Resize and position it however you like — the background "
            "stays transparent so only the bubble shows.\n\n"
            "*Tip: on iPhone, open the PNG in **Photos** → tap **Share** → "
            "**Copy Photo** → open your target photo in **Markup** → paste.*"
        )


def _make_checkered_preview(img: Image.Image, square: int = 12) -> Image.Image:
    """Composite the image over a checkered pattern so transparency is visible."""
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

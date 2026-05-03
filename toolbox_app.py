"""
Toolbox App
A multi-tool Streamlit application for image and file operations.

Tools:
    1. HEIC -> JPG/PNG converter (max quality, batch supported)
    2. iMessage Creator — generate single iMessage bubbles (sent / received /
       typing indicator) on a transparent background, ready to paste anywhere.
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
                        buf, format="JPEG", quality=100, subsampling=0,
                        optimize=True, exif=exif_bytes,
                    )
                    out_name = f"{stem}.jpg"
                    mime = "image/jpeg"
                else:
                    image.save(
                        buf, format="PNG", compress_level=6, optimize=True,
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
IMSG_BLUE = (10, 132, 255)
IMSG_GRAY = (229, 229, 234)
IMSG_TEXT_DARK = (0, 0, 0)
IMSG_TEXT_LIGHT = (255, 255, 255)
IMSG_DELIVERED_GRAY = (142, 142, 147)
IMSG_TYPING_DOT = (140, 140, 145)


def _wrap_text_to_width(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> List[str]:
    """Word-wrap respecting hard newlines."""
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


# --------------------------------------------------------------------------- #
# Bubble silhouette — the key to a correct iMessage look
# --------------------------------------------------------------------------- #
def _build_bubble_mask(
    bubble_w: int,
    bubble_h: int,
    *,
    side: str,
    corner_radius: int,
    tail_size: int,
    canvas_w: int,
    canvas_h: int,
    bubble_x: int,
    bubble_y: int,
) -> Image.Image:
    """
    Build a single mask (L mode, 8-bit) representing the entire bubble
    silhouette: rounded rectangle UNION a small tail curl on the bottom-
    outer corner. Drawing the bubble fill through this mask is what gives
    us the proper iMessage shape.

    The tail is composed of:
      * a primary rounded "lump" attached to the bottom-outer corner of
        the bubble, formed by an ellipse that overlaps the bubble corner
      * a tiny detached knob pixel further out (the iMessage "speech tail
        end")
    """
    mask = Image.new("L", (canvas_w, canvas_h), 0)
    md = ImageDraw.Draw(mask)

    # Main bubble rounded rectangle
    md.rounded_rectangle(
        [(bubble_x, bubble_y),
         (bubble_x + bubble_w - 1, bubble_y + bubble_h - 1)],
        radius=corner_radius,
        fill=255,
    )

    # Tail — primary lump.
    # Designed to attach seamlessly to the bottom-outer corner of the
    # bubble and bulge outward + slightly downward, forming the iMessage
    # "curl".
    lump_d = int(tail_size * 1.7)        # diameter of the lump
    knob_d = max(3, int(tail_size * 0.55))  # tiny separated knob

    if side == "right":
        # Lump: positioned so it overlaps the bubble's bottom-right corner.
        # Its center sits roughly on the bubble's bottom edge, just outside
        # the right edge.
        lump_cx = bubble_x + bubble_w - int(corner_radius * 0.05)
        lump_cy = bubble_y + bubble_h - int(lump_d * 0.45)
        md.ellipse(
            [(lump_cx - lump_d // 2, lump_cy - lump_d // 2),
             (lump_cx + lump_d // 2, lump_cy + lump_d // 2)],
            fill=255,
        )
        # Tiny knob — sits below-right of the lump, separated by transparent gap
        knob_cx = bubble_x + bubble_w + int(tail_size * 0.55)
        knob_cy = bubble_y + bubble_h + int(tail_size * 0.05)
        md.ellipse(
            [(knob_cx - knob_d // 2, knob_cy - knob_d // 2),
             (knob_cx + knob_d // 2, knob_cy + knob_d // 2)],
            fill=255,
        )
    else:
        lump_cx = bubble_x + int(corner_radius * 0.05)
        lump_cy = bubble_y + bubble_h - int(lump_d * 0.45)
        md.ellipse(
            [(lump_cx - lump_d // 2, lump_cy - lump_d // 2),
             (lump_cx + lump_d // 2, lump_cy + lump_d // 2)],
            fill=255,
        )
        knob_cx = bubble_x - int(tail_size * 0.55)
        knob_cy = bubble_y + bubble_h + int(tail_size * 0.05)
        md.ellipse(
            [(knob_cx - knob_d // 2, knob_cy - knob_d // 2),
             (knob_cx + knob_d // 2, knob_cy + knob_d // 2)],
            fill=255,
        )

    return mask


def _apply_subtle_blue_gradient(
    base: Image.Image,
    mask: Image.Image,
    *,
    color: Tuple[int, int, int],
) -> None:
    """Paint a flat color through the mask onto the base."""
    fill_layer = Image.new("RGBA", base.size, color + (255,))
    base.paste(fill_layer, (0, 0), mask)


# --------------------------------------------------------------------------- #
# Main bubble renderer
# --------------------------------------------------------------------------- #
def render_text_bubble(
    text: str,
    *,
    side: str,                           # "right" (blue/sent) or "left" (gray/received)
    font_size: int = 64,
    max_text_width_px: int | None = None,
    show_delivered: bool = True,
) -> Image.Image:
    """
    Render a single iMessage text bubble on a transparent background.
    Tightly cropped, returns RGBA. Padding / tail / radius all proportional
    to font_size, so proportions stay correct at any size.
    """
    # ---- Geometry, all proportional to font ------------------------------
    pad_x = int(font_size * 0.55)
    pad_y = int(font_size * 0.30)
    line_spacing = int(font_size * 0.18)
    tail_size = int(font_size * 0.35)

    if max_text_width_px is None:
        max_text_width_px = int(font_size * 14)  # sane default

    font = get_imessage_font(font_size)
    delivered_font = get_imessage_font(max(12, int(font_size * 0.40)))

    # ---- Measure text -----------------------------------------------------
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

    # iMessage corner radius:
    #   - small for tall/multi-line bubbles (rounded rectangle, ~18-22px in iOS at 1x)
    #   - capped at half height for short single-line bubbles (pill shape)
    # We use a fixed ratio of the FONT (not bubble height) so tall bubbles
    # don't over-round, and cap by half-height so short bubbles can still be pill-shaped.
    corner_radius = min(int(font_size * 0.95), bubble_h // 2)

    # ---- Canvas size -----------------------------------------------------
    margin = max(2, int(font_size * 0.10))
    tail_extra = int(tail_size * 1.6)  # room for lump + knob to extend past bubble

    delivered_h = 0
    if side == "right" and show_delivered:
        dbbox = sdraw.textbbox((0, 0), "Delivered", font=delivered_font)
        delivered_h = (dbbox[3] - dbbox[1]) + int(font_size * 0.30)

    canvas_w = bubble_w + tail_extra + 2 * margin
    canvas_h = bubble_h + tail_extra + delivered_h + 2 * margin

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # Position bubble so the tail has room to extend on the OUTER side
    if side == "right":
        bubble_x = margin
    else:
        bubble_x = margin + tail_extra
    bubble_y = margin

    # ---- Build mask + paint ----------------------------------------------
    mask = _build_bubble_mask(
        bubble_w, bubble_h,
        side=side,
        corner_radius=corner_radius,
        tail_size=tail_size,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        bubble_x=bubble_x,
        bubble_y=bubble_y,
    )

    if side == "right":
        _apply_subtle_blue_gradient(img, mask, color=IMSG_BLUE)
        text_color = IMSG_TEXT_LIGHT
    else:
        _apply_subtle_blue_gradient(img, mask, color=IMSG_GRAY)
        text_color = IMSG_TEXT_DARK

    # ---- Draw text -------------------------------------------------------
    draw = ImageDraw.Draw(img)
    ty = bubble_y + pad_y
    for ln in lines:
        tx = bubble_x + pad_x
        draw.text((tx, ty), ln, font=font, fill=text_color + (255,))
        ty += line_h + line_spacing

    # ---- "Delivered" — only on blue ---------------------------------------
    if side == "right" and show_delivered:
        dtext = "Delivered"
        dbbox = draw.textbbox((0, 0), dtext, font=delivered_font)
        dw = dbbox[2] - dbbox[0]
        dx = bubble_x + bubble_w - dw
        dy = bubble_y + bubble_h + int(font_size * 0.35)
        draw.text((dx, dy), dtext, font=delivered_font,
                  fill=IMSG_DELIVERED_GRAY + (255,))

    return _tight_crop(img)


def render_typing_bubble(
    *,
    font_size: int = 64,
) -> Image.Image:
    """
    Render the iMessage typing indicator (gray bubble with three animated
    dots — though we render a static frame). Returns RGBA, tightly cropped.

    Uses the same geometry rules as a text bubble but sized around the dots
    instead of text.
    """
    # The typing bubble in iMessage is roughly the size of a one-line gray
    # bubble. We use font_size as a proxy for "scale".
    pad_x = int(font_size * 0.55)
    pad_y = int(font_size * 0.40)
    tail_size = int(font_size * 0.35)

    # Three dots, sized as a fraction of font size.
    dot_d = int(font_size * 0.32)
    dot_gap = int(dot_d * 0.55)

    inner_w = 3 * dot_d + 2 * dot_gap
    inner_h = dot_d

    bubble_w = inner_w + 2 * pad_x
    bubble_h = inner_h + 2 * pad_y

    # Typing bubble is short — pill shape is correct
    corner_radius = bubble_h // 2

    margin = max(2, int(font_size * 0.10))
    tail_extra = int(tail_size * 1.6)

    canvas_w = bubble_w + tail_extra + 2 * margin
    canvas_h = bubble_h + tail_extra + 2 * margin

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # Typing bubble is always on the LEFT (received side) — the typing
    # indicator only shows for the other person.
    bubble_x = margin + tail_extra
    bubble_y = margin

    mask = _build_bubble_mask(
        bubble_w, bubble_h,
        side="left",
        corner_radius=corner_radius,
        tail_size=tail_size,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        bubble_x=bubble_x,
        bubble_y=bubble_y,
    )

    _apply_subtle_blue_gradient(img, mask, color=IMSG_GRAY)

    # ---- Draw the three dots ---------------------------------------------
    draw = ImageDraw.Draw(img)
    dots_total_w = 3 * dot_d + 2 * dot_gap
    start_x = bubble_x + (bubble_w - dots_total_w) // 2
    cy = bubble_y + bubble_h // 2

    for i in range(3):
        cx = start_x + i * (dot_d + dot_gap) + dot_d // 2
        draw.ellipse(
            [(cx - dot_d // 2, cy - dot_d // 2),
             (cx + dot_d // 2, cy + dot_d // 2)],
            fill=IMSG_TYPING_DOT + (255,),
        )

    return _tight_crop(img)


def _tight_crop(img: Image.Image) -> Image.Image:
    """Crop to non-transparent bbox plus a 2-pixel safety margin."""
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if not bbox:
        return img
    safety = 2
    w, h = img.size
    return img.crop((
        max(0, bbox[0] - safety),
        max(0, bbox[1] - safety),
        min(w, bbox[2] + safety),
        min(h, bbox[3] + safety),
    ))


def _make_checkered_preview(img: Image.Image, square: int = 12) -> Image.Image:
    """Composite over a checker pattern so transparency is visible."""
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
# iMessage Creator UI
# --------------------------------------------------------------------------- #
def imessage_creator_tab() -> None:
    st.header("iMessage Creator")
    st.caption(
        "Generate a single iMessage element on a transparent background. "
        "Download the PNG, then paste it on any photo and rescale freely "
        "in your editor."
    )

    bubble_type = st.radio(
        "Type",
        options=["Sent (blue)", "Reply (gray)", "Typing… (3 dots)"],
        horizontal=True,
    )

    font_size = st.slider(
        "Resolution (size in px)",
        min_value=32, max_value=200, value=80,
        help="Higher = larger PNG, sharper when scaled. "
             "You'll resize on your photo anyway, so just pick big enough.",
    )

    bubble: Image.Image | None = None
    download_filename = "imessage_bubble.png"

    if bubble_type == "Typing… (3 dots)":
        bubble = render_typing_bubble(font_size=font_size)
        download_filename = "imessage_typing.png"

    else:
        side = "right" if bubble_type.startswith("Sent") else "left"
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
            st.info("Type a message above to generate the bubble.")
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
            "4. Resize and position it however you like — the background "
            "stays transparent so only the bubble shows.\n\n"
            "*iPhone tip: open the PNG in **Photos** → tap **Share** → "
            "**Copy Photo** → open your target photo in **Markup** → paste.*"
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

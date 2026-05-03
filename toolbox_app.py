"""
Toolbox App
A multi-tool Streamlit application for image and file operations.

Tools:
    1. HEIC -> JPG/PNG converter (max quality)
    2. iMessage-style overlay generator (authentic iMessage look & feel)
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
    # First, look in the bundled ./fonts directory
    for name in filenames:
        candidate = FONT_DIR / name
        if candidate.exists():
            return str(candidate)
    # Fall back to common system locations (works on most Linux/macOS)
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


def get_imessage_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """
    Load the closest-to-SF-Pro font available.
    Priority:
      1. Bundled SF Pro / SFPro-Text (if present in ./fonts)
      2. Inter (Google Fonts) — modern, similar metrics
      3. DejaVu Sans (always available on Streamlit Cloud / Linux)
    """
    if weight == "bold":
        candidates = [
            "SF-Pro-Text-Bold.otf", "SFProText-Bold.otf", "SFProDisplay-Bold.otf",
            "Inter-Bold.ttf", "Inter-Bold.otf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "SF-Pro-Text-Regular.otf", "SFProText-Regular.otf", "SFProDisplay-Regular.otf",
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
    st.caption("Convert HEIC / HEIF photos to JPG or PNG at maximum quality.")

    if not HEIC_SUPPORT:
        st.error(
            "HEIC support is not installed. Add `pillow-heif` to requirements.txt."
        )
        return

    uploaded_files = st.file_uploader(
        "Drop one or more HEIC files",
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
        st.info("Upload HEIC files above to begin.")
        return

    if st.button("Convert", type="primary", use_container_width=True):
        progress = st.progress(0.0)
        results: List[Tuple[str, bytes, str]] = []  # (filename, bytes, mime)

        for i, up in enumerate(uploaded_files, start=1):
            try:
                image = Image.open(up)
                # Preserve EXIF if present
                exif_bytes = image.info.get("exif", b"")

                buf = io.BytesIO()
                stem = Path(up.name).stem

                if output_format == "JPG":
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    image.save(
                        buf,
                        format="JPEG",
                        quality=100,           # maximum quality
                        subsampling=0,         # 4:4:4, no chroma downsampling
                        optimize=True,
                        exif=exif_bytes,
                    )
                    out_name = f"{stem}.jpg"
                    mime = "image/jpeg"
                else:  # PNG — lossless
                    image.save(
                        buf,
                        format="PNG",
                        compress_level=6,      # balanced; lossless either way
                        optimize=True,
                    )
                    out_name = f"{stem}.png"
                    mime = "image/png"

                results.append((out_name, buf.getvalue(), mime))
            except Exception as e:
                st.error(f"Failed to convert {up.name}: {e}")

            progress.progress(i / len(uploaded_files))

        progress.empty()

        if results:
            st.success(f"Converted {len(results)} file(s).")
            for name, data, mime in results:
                st.download_button(
                    label=f"⬇️  Download {name}",
                    data=data,
                    file_name=name,
                    mime=mime,
                    key=f"dl_{name}",
                    use_container_width=True,
                )

            # Bundle as ZIP if more than one
            if len(results) > 1:
                import zipfile
                zbuf = io.BytesIO()
                with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, data, _ in results:
                        zf.writestr(name, data)
                st.download_button(
                    label=f"⬇️  Download all as ZIP",
                    data=zbuf.getvalue(),
                    file_name="converted.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                )


# --------------------------------------------------------------------------- #
# Tool 2: iMessage Overlay
# --------------------------------------------------------------------------- #

# Authentic iMessage colors (sampled from iOS)
IMSG_BLUE_TOP = (10, 132, 255)       # gradient top — sent bubble
IMSG_BLUE_BOTTOM = (0, 122, 255)     # gradient bottom — sent bubble
IMSG_GRAY = (229, 229, 234)          # received bubble
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


def _draw_bubble(
    base: Image.Image,
    text: str,
    *,
    side: str,                       # "left" or "right"
    top_y: int,
    canvas_width: int,
    font: ImageFont.FreeTypeFont,
    scale: float,
) -> int:
    """
    Draw a single iMessage-style bubble onto `base`.
    Returns the y-coordinate immediately below the drawn bubble.
    """
    # Layout constants, scaled
    side_margin = int(18 * scale)
    bubble_padding_x = int(16 * scale)
    bubble_padding_y = int(9 * scale)
    line_spacing = int(4 * scale)
    tail_size = int(11 * scale)
    # Reserve room on the outer side so the tail doesn't get clipped
    outer_reserve = tail_size + int(4 * scale)
    max_bubble_width = int(canvas_width * 0.72)

    # Use a transparent overlay so bubbles can sit on any photo
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Wrap text
    inner_max_w = max_bubble_width - 2 * bubble_padding_x
    lines = _wrap_text_to_width(text, font, inner_max_w, draw)
    if not lines:
        lines = [""]

    # Measure
    line_heights: List[int] = []
    line_widths: List[int] = []
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln if ln else " ", font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    text_w = max(line_widths) if line_widths else 0
    # Use font ascent/descent for stable line height
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    text_h = line_h * len(lines) + line_spacing * (len(lines) - 1)

    bubble_w = text_w + 2 * bubble_padding_x
    bubble_h = text_h + 2 * bubble_padding_y

    # iMessage corner radius is roughly half the bubble height (pill ends),
    # capped so it never exceeds half the bubble width either.
    corner_radius = min(bubble_h // 2, bubble_w // 2)

    # Position bubble — leave room on the outer side for the tail
    if side == "right":
        bubble_x1 = canvas_width - side_margin - outer_reserve - bubble_w
    else:
        bubble_x1 = side_margin + outer_reserve
    bubble_y1 = top_y
    bubble_x2 = bubble_x1 + bubble_w
    bubble_y2 = bubble_y1 + bubble_h

    # ---- Bubble fill ------------------------------------------------------
    if side == "right":
        # Vertical gradient blue (subtle, matches iOS rendering on long bubbles)
        grad = Image.new("RGBA", (bubble_w, bubble_h), IMSG_BLUE_BOTTOM + (255,))
        gd = ImageDraw.Draw(grad)
        for y in range(bubble_h):
            t = y / max(1, bubble_h - 1)
            r = int(IMSG_BLUE_TOP[0] * (1 - t) + IMSG_BLUE_BOTTOM[0] * t)
            g = int(IMSG_BLUE_TOP[1] * (1 - t) + IMSG_BLUE_BOTTOM[1] * t)
            b = int(IMSG_BLUE_TOP[2] * (1 - t) + IMSG_BLUE_BOTTOM[2] * t)
            gd.line([(0, y), (bubble_w, y)], fill=(r, g, b, 255))

        # Mask for rounded rectangle
        mask = Image.new("L", (bubble_w, bubble_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [(0, 0), (bubble_w - 1, bubble_h - 1)],
            radius=corner_radius,
            fill=255,
        )
        overlay.paste(grad, (bubble_x1, bubble_y1), mask)
        text_color = IMSG_TEXT_LIGHT
    else:
        draw.rounded_rectangle(
            [(bubble_x1, bubble_y1), (bubble_x2, bubble_y2)],
            radius=corner_radius,
            fill=IMSG_GRAY + (255,),
        )
        text_color = IMSG_TEXT_DARK

    # ---- Bubble tail ------------------------------------------------------
    # The iMessage tail is a small curved hook on the bottom-outer corner.
    # We approximate it as an ellipse-shaped lobe that pokes out from the
    # corner, plus a small detached "knob" further out for the classic look.
    tail_color = IMSG_BLUE_BOTTOM if side == "right" else IMSG_GRAY
    lobe_w = int(tail_size * 1.4)
    lobe_h = int(tail_size * 1.6)
    knob_r = max(2, int(tail_size * 0.32))

    if side == "right":
        # Lobe overlaps the bottom-right corner of the bubble
        lobe_cx = bubble_x2 + int(tail_size * 0.2)
        lobe_cy = bubble_y2 - int(lobe_h * 0.45)
        draw.ellipse(
            [(lobe_cx - lobe_w // 2, lobe_cy - lobe_h // 2),
             (lobe_cx + lobe_w // 2, lobe_cy + lobe_h // 2)],
            fill=tail_color + (255,),
        )
        # Detached knob slightly further out and down
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
    ty = bubble_y1 + bubble_padding_y
    for i, ln in enumerate(lines):
        lw = line_widths[i]
        if side == "right":
            # Right-align inside bubble looks wrong; iMessage left-aligns text
            tx = bubble_x1 + bubble_padding_x
        else:
            tx = bubble_x1 + bubble_padding_x
        draw.text((tx, ty), ln, font=font, fill=text_color + (255,))
        ty += line_h + line_spacing

    # Composite overlay onto base
    base.alpha_composite(overlay)

    return bubble_y2


def _draw_double_check(
    draw: ImageDraw.ImageDraw,
    *,
    cx: int,
    cy: int,
    size: int,
    color: Tuple[int, int, int],
) -> int:
    """Draw two overlapping blue checkmarks (iMessage 'delivered'/read icon).
    Returns the total width consumed."""
    stroke = max(2, int(size * 0.16))
    # In iMessage the two checks overlap by about half a check-width
    spacing = max(int(size * 0.42), stroke + 1)
    total_w = size + spacing
    for offset in (0, spacing):
        x0 = cx + offset
        # Left stroke (down to bottom-mid)
        draw.line(
            [(x0, cy + size * 0.50),
             (x0 + size * 0.30, cy + size * 0.85)],
            fill=color + (255,), width=stroke,
        )
        # Right stroke (up to top-right)
        draw.line(
            [(x0 + size * 0.30, cy + size * 0.85),
             (x0 + size * 0.95, cy + size * 0.10)],
            fill=color + (255,), width=stroke,
        )
    return total_w


def _draw_delivered(
    base: Image.Image,
    *,
    bottom_y: int,
    canvas_width: int,
    font: ImageFont.FreeTypeFont,
    scale: float,
) -> None:
    """Draw the small 'Delivered ✓✓' indicator under the last sent bubble."""
    side_margin = int(18 * scale)
    text = "Delivered"
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    check_size = int(th * 0.85)
    check_gap = int(4 * scale)
    check_w_estimate = check_size + int(check_size * 0.55)

    group_w = tw + check_gap + check_w_estimate
    group_x = canvas_width - side_margin - group_w
    ty = bottom_y + int(6 * scale)

    draw.text((group_x, ty), text, font=font, fill=IMSG_DELIVERED_GRAY + (255,))
    _draw_double_check(
        draw,
        cx=group_x + tw + check_gap,
        cy=ty,
        size=check_size,
        color=IMSG_BLUE_BOTTOM,
    )

    base.alpha_composite(overlay)


def imessage_overlay_tab() -> None:
    st.header("iMessage Overlay")
    st.caption("Drop your photo, write the conversation, position it, export.")

    uploaded = st.file_uploader(
        "Background photo",
        type=["jpg", "jpeg", "png", "webp"],
        key="imsg_uploader",
    )

    st.markdown("**Conversation**")
    st.caption(
        "One message per line. Prefix with `>` for a sent (blue) message, "
        "or leave plain for a received (gray) message."
    )
    default_convo = (
        "I had a dream about you last night\n"
        "> Was I starting a task and ACTUALLY finishing it??\n"
        "No\n"
        "> Wasn't me"
    )
    convo_text = st.text_area(
        "Messages",
        value=default_convo,
        height=160,
        label_visibility="collapsed",
    )

    col1, col2 = st.columns(2)
    with col1:
        vertical_pos = st.slider(
            "Vertical position",
            min_value=0,
            max_value=100,
            value=30,
            help="Where the conversation block starts (0 = top, 100 = bottom).",
        )
    with col2:
        bubble_scale = st.slider(
            "Bubble size",
            min_value=0.5,
            max_value=2.0,
            value=1.0,
            step=0.05,
        )

    show_delivered = st.checkbox("Show 'Delivered' under the last sent message", value=True)

    if not uploaded:
        st.info("Upload a background photo to start.")
        return

    # Load base image
    base = Image.open(uploaded).convert("RGBA")
    canvas_width, canvas_height = base.size

    # Choose a base font size proportional to image width, then apply scale.
    base_font_size = max(14, int(canvas_width * 0.032))
    font_size = int(base_font_size * bubble_scale)
    font = get_imessage_font(font_size)
    delivered_font = get_imessage_font(max(10, int(font_size * 0.62)))

    # Parse conversation
    messages: List[Tuple[str, str]] = []  # (side, text)
    for raw in convo_text.split("\n"):
        if not raw.strip():
            continue
        if raw.lstrip().startswith(">"):
            messages.append(("right", raw.lstrip()[1:].lstrip()))
        else:
            messages.append(("left", raw))

    if not messages:
        st.warning("Add at least one message.")
        return

    # Estimate where to start drawing (vertical_pos is % from top)
    starting_y = int(canvas_height * vertical_pos / 100)
    # Clamp so bubbles don't start so low they get cut off (rough estimate)
    estimated_block_height = len(messages) * int(font_size * 3.0)
    if starting_y + estimated_block_height > canvas_height:
        starting_y = max(0, canvas_height - estimated_block_height - int(40 * bubble_scale))

    # Draw all bubbles
    cursor_y = starting_y
    last_right_bottom = None
    bubble_gap = int(font_size * 0.55)

    for side, msg in messages:
        cursor_y = _draw_bubble(
            base,
            msg,
            side=side,
            top_y=cursor_y,
            canvas_width=canvas_width,
            font=font,
            scale=bubble_scale,
        )
        if side == "right":
            last_right_bottom = cursor_y
        cursor_y += bubble_gap

    # Delivered indicator under the last sent (right) bubble
    if show_delivered and last_right_bottom is not None:
        # Only show if the LAST message overall is a sent one (matches iMessage)
        if messages[-1][0] == "right":
            _draw_delivered(
                base,
                bottom_y=last_right_bottom,
                canvas_width=canvas_width,
                font=delivered_font,
                scale=bubble_scale,
            )

    # Preview
    st.image(base, use_container_width=True, caption="Preview")

    # Download
    out_format = st.radio(
        "Download format",
        options=["PNG", "JPG"],
        horizontal=True,
        key="imsg_dl_format",
    )

    buf = io.BytesIO()
    if out_format == "PNG":
        base.save(buf, format="PNG", optimize=True)
        mime = "image/png"
        ext = "png"
    else:
        base.convert("RGB").save(
            buf, format="JPEG", quality=100, subsampling=0, optimize=True
        )
        mime = "image/jpeg"
        ext = "jpg"

    st.download_button(
        label=f"⬇️  Download as {out_format}",
        data=buf.getvalue(),
        file_name=f"imessage_overlay.{ext}",
        mime=mime,
        type="primary",
        use_container_width=True,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("🧰 Toolbox")
    st.caption("A small collection of file & image utilities.")

    tab1, tab2 = st.tabs(["HEIC → JPG/PNG", "iMessage Overlay"])
    with tab1:
        heic_converter_tab()
    with tab2:
        imessage_overlay_tab()


if __name__ == "__main__":
    main()

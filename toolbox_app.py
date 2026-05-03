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
    layout="wide",
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


def get_imessage_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """Load the closest-to-SF-Pro font available."""
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
        results: List[Tuple[str, bytes, str]] = []

        for i, up in enumerate(uploaded_files, start=1):
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

            if len(results) > 1:
                import zipfile
                zbuf = io.BytesIO()
                with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, data, _ in results:
                        zf.writestr(name, data)
                st.download_button(
                    label="⬇️  Download all as ZIP",
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


def _draw_double_check(
    draw: ImageDraw.ImageDraw,
    *,
    cx: int,
    cy: int,
    size: int,
    color: Tuple[int, int, int],
) -> int:
    """Draw two overlapping blue checkmarks. Returns total width consumed."""
    stroke = max(2, int(size * 0.16))
    spacing = max(int(size * 0.42), stroke + 1)
    total_w = size + spacing
    for offset in (0, spacing):
        x0 = cx + offset
        draw.line(
            [(x0, cy + size * 0.50),
             (x0 + size * 0.30, cy + size * 0.85)],
            fill=color + (255,), width=stroke,
        )
        draw.line(
            [(x0 + size * 0.30, cy + size * 0.85),
             (x0 + size * 0.95, cy + size * 0.10)],
            fill=color + (255,), width=stroke,
        )
    return total_w


def _draw_bubble(
    base: Image.Image,
    text: str,
    *,
    side: str,
    top_y: int,
    x_offset: int,
    canvas_width: int,
    font: ImageFont.FreeTypeFont,
) -> Tuple[int, int, int]:
    """
    Draw a single iMessage-style bubble.
    Padding and tail size scale with the FONT, not the image. So the
    bubble proportions stay correct regardless of font_size or image size.
    Returns (bubble_y2, bubble_x2, bubble_y2).
    """
    font_size = font.size
    bubble_padding_x = int(font_size * 0.55)
    bubble_padding_y = int(font_size * 0.35)
    line_spacing = int(font_size * 0.18)
    tail_size = int(font_size * 0.40)
    outer_reserve = tail_size + int(font_size * 0.20)
    side_margin = int(font_size * 0.70)

    max_bubble_width = int(canvas_width * 0.72)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    inner_max_w = max_bubble_width - 2 * bubble_padding_x
    lines = _wrap_text_to_width(text, font, inner_max_w, draw)
    if not lines:
        lines = [""]

    line_widths = []
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln if ln else " ", font=font)
        line_widths.append(bbox[2] - bbox[0])
    text_w = max(line_widths) if line_widths else 0

    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    text_h = line_h * len(lines) + line_spacing * (len(lines) - 1)

    bubble_w = text_w + 2 * bubble_padding_x
    bubble_h = text_h + 2 * bubble_padding_y

    corner_radius = min(bubble_h // 2, bubble_w // 2)

    if side == "right":
        bubble_x1 = canvas_width - side_margin - outer_reserve - bubble_w + x_offset
    else:
        bubble_x1 = side_margin + outer_reserve + x_offset
    bubble_y1 = top_y
    bubble_x2 = bubble_x1 + bubble_w
    bubble_y2 = bubble_y1 + bubble_h

    # Fill
    if side == "right":
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
        overlay.paste(grad, (bubble_x1, bubble_y1), mask)
        text_color = IMSG_TEXT_LIGHT
    else:
        draw.rounded_rectangle(
            [(bubble_x1, bubble_y1), (bubble_x2, bubble_y2)],
            radius=corner_radius,
            fill=IMSG_GRAY + (255,),
        )
        text_color = IMSG_TEXT_DARK

    # Tail
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

    # Text
    ty = bubble_y1 + bubble_padding_y
    for ln in lines:
        tx = bubble_x1 + bubble_padding_x
        draw.text((tx, ty), ln, font=font, fill=text_color + (255,))
        ty += line_h + line_spacing

    base.alpha_composite(overlay)

    return bubble_y2, bubble_x2, bubble_y2


def _draw_delivered(
    base: Image.Image,
    *,
    bottom_y: int,
    right_edge: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    """Draw 'Delivered ✓✓' aligned to the right edge of the last sent bubble."""
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    text = "Delivered"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    check_size = int(th * 0.85)
    check_gap = max(3, int(font.size * 0.18))
    check_w_estimate = check_size + int(check_size * 0.55)

    group_w = tw + check_gap + check_w_estimate
    group_x = right_edge - group_w
    ty = bottom_y + int(font.size * 0.25)

    draw.text((group_x, ty), text, font=font, fill=IMSG_DELIVERED_GRAY + (255,))
    _draw_double_check(
        draw,
        cx=group_x + tw + check_gap,
        cy=ty,
        size=check_size,
        color=IMSG_BLUE_BOTTOM,
    )

    base.alpha_composite(overlay)


def _ensure_messages_state() -> None:
    if "imsg_messages" not in st.session_state:
        st.session_state.imsg_messages = [
            {"side": "left",  "text": "I had a dream about you last night",     "dx": 0, "dy": 0},
            {"side": "right", "text": "Was I starting a task and ACTUALLY finishing it??", "dx": 0, "dy": 0},
            {"side": "left",  "text": "No",                                     "dx": 0, "dy": 0},
            {"side": "right", "text": "Wasn't me",                              "dx": 0, "dy": 0},
        ]


def imessage_overlay_tab() -> None:
    st.header("iMessage Overlay")
    st.caption("Drop your photo, edit each message, position them individually, export.")

    _ensure_messages_state()

    left_col, right_col = st.columns([1, 1])

    # ============== LEFT — controls ========================================
    with left_col:
        uploaded = st.file_uploader(
            "Background photo",
            type=["jpg", "jpeg", "png", "webp"],
            key="imsg_uploader",
        )

        if not uploaded:
            st.info("Upload a background photo to start.")
            return

        base_preview = Image.open(uploaded).convert("RGBA")
        W, H = base_preview.size

        st.markdown("### Global settings")

        default_font_size = max(28, int(W * 0.038))
        font_size = st.slider(
            "Bubble / font size (px)",
            min_value=14,
            max_value=200,
            value=default_font_size,
            help="Padding and tail scale automatically with the font, "
                 "so bubble proportions stay correct.",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            global_x = st.slider(
                "Move all (X)", min_value=-W // 2, max_value=W // 2, value=0,
            )
        with col_b:
            global_y = st.slider(
                "Move all (Y)", min_value=0, max_value=H, value=int(H * 0.30),
                help="Vertical position of the first bubble (px from top).",
            )

        bubble_gap = st.slider(
            "Gap between messages (px)",
            min_value=0, max_value=80, value=int(font_size * 0.45),
        )

        show_delivered = st.checkbox(
            "Show 'Delivered' under the last sent message", value=True,
        )

        st.divider()

        st.markdown("### Messages")
        st.caption("Edit text, swap side, reorder, and nudge position per bubble.")

        msgs = st.session_state.imsg_messages
        to_delete = None

        for i, m in enumerate(msgs):
            label_side = "🟦 sent" if m["side"] == "right" else "⬜ received"
            preview_text = m["text"][:30] + ("…" if len(m["text"]) > 30 else "")
            with st.expander(f"#{i + 1} — {label_side} — \"{preview_text}\""):
                m["text"] = st.text_area(
                    "Text", value=m["text"], key=f"text_{i}", height=70,
                )
                m["side"] = st.radio(
                    "Side",
                    options=["left", "right"],
                    format_func=lambda s: "Received (gray, left)" if s == "left"
                                          else "Sent (blue, right)",
                    horizontal=True,
                    index=0 if m["side"] == "left" else 1,
                    key=f"side_{i}",
                )
                cx, cy = st.columns(2)
                with cx:
                    m["dx"] = st.slider(
                        "Nudge X (px)",
                        min_value=-W // 2, max_value=W // 2,
                        value=int(m.get("dx", 0)),
                        key=f"dx_{i}",
                    )
                with cy:
                    m["dy"] = st.slider(
                        "Nudge Y (px)",
                        min_value=-H // 2, max_value=H // 2,
                        value=int(m.get("dy", 0)),
                        key=f"dy_{i}",
                    )
                btn_cols = st.columns(4)
                with btn_cols[0]:
                    if st.button("⬆ Up", key=f"up_{i}", disabled=(i == 0),
                                 use_container_width=True):
                        msgs[i - 1], msgs[i] = msgs[i], msgs[i - 1]
                        st.rerun()
                with btn_cols[1]:
                    if st.button("⬇ Down", key=f"down_{i}",
                                 disabled=(i == len(msgs) - 1),
                                 use_container_width=True):
                        msgs[i + 1], msgs[i] = msgs[i], msgs[i + 1]
                        st.rerun()
                with btn_cols[2]:
                    if st.button("Reset nudge", key=f"reset_{i}",
                                 use_container_width=True):
                        m["dx"] = 0
                        m["dy"] = 0
                        st.rerun()
                with btn_cols[3]:
                    if st.button("🗑 Delete", key=f"del_{i}",
                                 use_container_width=True):
                        to_delete = i

        if to_delete is not None:
            msgs.pop(to_delete)
            st.rerun()

        add_cols = st.columns(2)
        with add_cols[0]:
            if st.button("➕ Add received (gray)", use_container_width=True):
                msgs.append({"side": "left", "text": "New message", "dx": 0, "dy": 0})
                st.rerun()
        with add_cols[1]:
            if st.button("➕ Add sent (blue)", use_container_width=True,
                         type="primary"):
                msgs.append({"side": "right", "text": "New message", "dx": 0, "dy": 0})
                st.rerun()

    # ============== RIGHT — preview ========================================
    with right_col:
        st.markdown("### Preview")

        if not st.session_state.imsg_messages:
            st.warning("Add at least one message.")
            return

        base = base_preview.copy()
        font = get_imessage_font(font_size)
        delivered_font = get_imessage_font(max(10, int(font_size * 0.55)))

        cursor_y = global_y
        last_right_info: Tuple[int, int] | None = None

        for m in st.session_state.imsg_messages:
            if not m["text"].strip():
                continue
            top_y = cursor_y + m.get("dy", 0)
            bottom_y, bx2, by2 = _draw_bubble(
                base,
                m["text"],
                side=m["side"],
                top_y=top_y,
                x_offset=global_x + m.get("dx", 0),
                canvas_width=W,
                font=font,
            )
            if m["side"] == "right":
                last_right_info = (by2, bx2)
            # Cursor advances by natural height + gap (independent of dy nudges)
            cursor_y = bottom_y - m.get("dy", 0) + bubble_gap

        if (
            show_delivered
            and last_right_info is not None
            and st.session_state.imsg_messages[-1]["side"] == "right"
        ):
            _draw_delivered(
                base,
                bottom_y=last_right_info[0],
                right_edge=last_right_info[1],
                font=delivered_font,
            )

        st.image(base, use_container_width=True)

        st.divider()

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

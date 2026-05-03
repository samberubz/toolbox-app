"""
Toolbox App
A multi-tool Streamlit application for image and file operations.

Tools:
    1. HEIC -> JPG/PNG converter (max quality)
"""

import io
from pathlib import Path
from typing import List, Tuple

import streamlit as st
from PIL import Image

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
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("🧰 Toolbox")
    st.caption("A small collection of file & image utilities.")

    tab1, = st.tabs(["HEIC → JPG/PNG"])
    with tab1:
        heic_converter_tab()


if __name__ == "__main__":
    main()

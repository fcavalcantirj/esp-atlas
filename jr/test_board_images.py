"""extract_images — the pinout diagram + board photo, resolved to absolute URLs.
Cite-or-omit: only what the doc links; None when there's no board imagery."""
import board_backfill as bb

DOC = "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitc-02/user_guide.html"
HTML = (
    '<img src="../_static/espressif-logo.svg">'
    '<img src="../_images/esp32-c3-devkitc-02-v1-isometric.png">'
    '<img src="../_images/esp32-c3-devkitc-02-v1-annotated-photo.png">'
    '<img src="../_images/esp32-c3-devkitc-02-v1-block-diags.png">'
    '<img src="../_images/esp32-c3-devkitc-02-v1-pinout.png">'
)


def test_resolves_pinout_and_photo_to_absolute_urls():
    imgs = bb.extract_images(HTML, DOC)
    assert imgs["pinout"] == "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/_images/esp32-c3-devkitc-02-v1-pinout.png"
    assert imgs["photo"].endswith("esp32-c3-devkitc-02-v1-isometric.png")   # first photo-ish match wins
    assert imgs["photo"].startswith("https://docs.espressif.com/")


def test_none_when_no_board_imagery():
    assert bb.extract_images('<img src="../_static/espressif-logo.svg">', DOC) is None
    assert bb.extract_images("", DOC) is None

# Contour regression fixture

`body_mask_20260924.json` contains only the external contour coordinates of the
large body triangle in the user-provided `Actual detection mask_screenshot_24.09.2026.png`.
Extraction: grayscale image, OpenCV RETR_EXTERNAL / CHAIN_APPROX_SIMPLE;
bounding box `(149, 304, 222, 122)`, raw contour area 12632 pixels².

This reproduces the failed edge fit without relying on a local Downloads path.
It is a mask screenshot, not the raw camera image or saved calibration profile;
passing this regression does not establish that the full calibration passes.

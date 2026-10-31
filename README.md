# PixelLab

Web image processing application. Upload images, choose Light / Medium / Heavy, preview and download processed images.

## Deploy to Render
- Runtime: Python
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT`

This project provides image adjustments, not verification of camera authenticity.

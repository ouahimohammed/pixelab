from flask import Flask, request, render_template, send_file, jsonify
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import numpy as np
import os
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 35_000_000
CONFIGS = {
 "light": dict(noise=1.5, contrast=1.03, saturation=1.01, brightness=1.02, blur=.2, sharpen=.5, resize=.99, low=88, high=96),
 "medium": dict(noise=2.5, contrast=1.05, saturation=1.03, brightness=1.03, blur=.3, sharpen=.8, resize=.97, low=80, high=94),
 "heavy": dict(noise=4., contrast=1.08, saturation=1.05, brightness=1.04, blur=.5, sharpen=1.2, resize=.95, low=72, high=92)
}
ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
def process_image(data, strength="medium", metadata_only=False):
    if strength not in CONFIGS:
        raise ValueError("Invalid processing strength")
    with Image.open(BytesIO(data)) as src:
        src.verify()
    with Image.open(BytesIO(data)) as src:
        if src.width * src.height > 35_000_000:
            raise ValueError("Image exceeds 35 million pixels")
        src = ImageOps.exif_transpose(src)
        if src.mode in ("RGBA", "LA") or "transparency" in src.info:
            rgba = src.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, "white")
            bg.alpha_composite(rgba)
            img = bg.convert("RGB")
        else:
            img = src.convert("RGB")
    cfg = CONFIGS[strength]
    if not metadata_only:
        arr = np.asarray(img, dtype=np.float32)
        rng = np.random.default_rng()
        arr += rng.normal(0, cfg["noise"], arr.shape)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        img = ImageEnhance.Contrast(img).enhance(cfg["contrast"])
        img = ImageEnhance.Color(img).enhance(cfg["saturation"])
        img = ImageEnhance.Brightness(img).enhance(cfg["brightness"])
        img = img.filter(ImageFilter.GaussianBlur(cfg["blur"]))
        img = img.filter(ImageFilter.UnsharpMask(radius=cfg["sharpen"], percent=120, threshold=3))
        original_size = img.size
        smaller = (max(1, int(img.width * cfg["resize"])), max(1, int(img.height * cfg["resize"])))
        img = img.resize(smaller, Image.Resampling.LANCZOS).resize(original_size, Image.Resampling.LANCZOS)
        temp = BytesIO()
        img.save(temp, "JPEG", quality=cfg["low"], optimize=True)
        temp.seek(0)
        with Image.open(temp) as compressed:
            img = compressed.copy()
    output = BytesIO()
    img.save(output, "JPEG", quality=cfg["high"], optimize=True)
    return output.getvalue()
@app.get("/")
def home():
    return render_template("index.html")
@app.get("/health")
def health():
    return jsonify(status="ok")
@app.post("/process")
def process():
    files = request.files.getlist("images")
    if not files or len(files) > 20:
        return jsonify(error="Choose between 1 and 20 images"), 400
    strength = request.form.get("strength", "medium")
    if strength not in CONFIGS:
        return jsonify(error="Invalid processing level"), 400
    metadata_only = request.form.get("metadata_only") == "true"
    results = []
    for i, uploaded in enumerate(files):
        ext = os.path.splitext(uploaded.filename or "")[1].lower()
        if ext not in ALLOWED:
            return jsonify(error="Unsupported image format"), 400
        try:
            data = uploaded.read()
            if len(data) > 25 * 1024 * 1024:
                return jsonify(error="Each image must be under 25 MB"), 400
            results.append((f"processed_{i+1}.jpg", process_image(data, strength, metadata_only)))
        except (UnidentifiedImageError, OSError, ValueError) as e:
            return jsonify(error=f"Image {i+1}: {e}"), 400
    if len(results) == 1:
        return send_file(BytesIO(results[0][1]), mimetype="image/jpeg", as_attachment=True, download_name=results[0][0])
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for filename, data in results:
            archive.writestr(filename, data)
    output.seek(0)
    return send_file(output, mimetype="application/zip", as_attachment=True, download_name="pixellab_results.zip")
@app.errorhandler(413)
def too_large(error):
    return jsonify(error="Upload exceeds 80 MB"), 413
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

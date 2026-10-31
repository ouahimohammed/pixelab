"""Web adapter for the unchanged upstream scripts/deai.py CLI."""
from flask import Flask, request, render_template, send_file, jsonify
from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import subprocess
import sys
import os

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024
SCRIPT = Path(__file__).resolve().parent / "scripts" / "deai.py"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify(status="ok", engine="upstream deai.py")

@app.post("/process")
def process():
    uploads = request.files.getlist("images")
    strength = request.form.get("strength", "medium")
    metadata_only = request.form.get("metadata_only") == "true"
    if strength not in {"light", "medium", "heavy"}:
        return jsonify(error="Invalid strength"), 400
    if not uploads or len(uploads) > 20:
        return jsonify(error="Choose 1–20 images"), 400
    results = []
    with TemporaryDirectory(prefix="pixellab_") as directory:
        folder = Path(directory)
        for index, upload in enumerate(uploads, 1):
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in EXTENSIONS:
                return jsonify(error=f"Unsupported file type: {suffix}"), 400
            data = upload.read(25 * 1024 * 1024 + 1)
            if not data or len(data) > 25 * 1024 * 1024:
                return jsonify(error="Each image must be 25 MB or less"), 400
            source = folder / f"source_{index}{suffix}"
            target = folder / f"processed_{index}.jpg"
            source.write_bytes(data)
            command = [sys.executable, str(SCRIPT), str(source), "-o", str(target), "--strength", strength, "--quiet"]
            if metadata_only:
                command.append("--no-metadata")
            try:
                run = subprocess.run(command, capture_output=True, text=True, timeout=100, cwd=folder, env={**os.environ, "TMPDIR": str(folder), "TMP": str(folder), "TEMP": str(folder), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
            except subprocess.TimeoutExpired:
                return jsonify(error=f"Image {index}: processing timed out"), 504
            if run.returncode != 0 or not target.exists():
                message = (run.stderr or run.stdout or "Unknown processing error").strip()
                return jsonify(error=f"Image {index}: {message[-500:]}"), 400
            results.append((target.name, target.read_bytes()))
    if len(results) == 1:
        return send_file(BytesIO(results[0][1]), mimetype="image/jpeg", as_attachment=True, download_name=results[0][0])
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, data in results:
            archive.writestr(name, data)
    output.seek(0)
    return send_file(output, mimetype="application/zip", as_attachment=True, download_name="pixellab_results.zip")

@app.errorhandler(413)
def too_large(error):
    return jsonify(error="Total upload exceeds 80 MB"), 413

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

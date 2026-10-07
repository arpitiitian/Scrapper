from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from scraper import scrape_paper
from pathlib import Path
from urllib.parse import unquote

app = Flask(__name__)
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.post("/scrape")
def scrape():
    url = request.form.get("url", "").strip()
    subject = request.form.get("subject", "").strip()
    if not url or not subject:
        return jsonify({"ok": False, "error": "URL aur Subject dono enter karo."}), 400
    try:
        result = scrape_paper(url, subject, DATA_DIR)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/data/<subject>/<paper>/<path:filename>")
def serve_data(subject, paper, filename):
    folder = DATA_DIR / unquote(subject) / unquote(paper)
    if not folder.exists(): abort(404)
    return send_from_directory(folder, filename)

@app.route("/view/<subject>/<paper>")
def view_paper(subject, paper):
    return render_template("view.html", subject=unquote(subject), paper=unquote(paper))

if __name__ == "__main__":
    print("QuizPractice Scraper: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)

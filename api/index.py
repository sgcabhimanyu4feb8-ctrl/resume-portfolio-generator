import os
import json
from flask import Flask, request, render_template, jsonify, make_response
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()
# Vercel requires specific absolute paths for templates and static files
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
template_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
THEME_TEMPLATES = {
    "dark": "portfolio_dark.html",
    "light": "portfolio_light.html",
    "creative": "portfolio_creative.html",
}
def build_prompt(resume_text: str, field: str, tone: str) -> str:
    tone_instructions = {
        "professional": "Use formal, achievement-focused language. Quantify impact where possible.",
        "casual": "Use friendly, approachable language while still sounding competent.",
        "academic": "Use precise, research-oriented language emphasizing depth and rigor.",
    }
    tone_note = tone_instructions.get(tone, tone_instructions["professional"])
    return f"""
You are an elite career coach and resume expert specializing in '{field}' careers.
Your task: extract and rewrite the user's resume into a structured JSON portfolio.
TONE INSTRUCTION: {tone_note}
STRICT RULES:
1. GROUNDING: Use ONLY facts explicitly stated in the resume. Do NOT invent names, companies, dates, or metrics.
2. REWRITING: Rewrite 'summary' and experience 'highlights' to be compelling for a '{field}' role, but only using real information.
3. MISSING DATA: Use empty string "" for missing text fields, and empty array [] for missing list fields. Never use null.
4. SKILLS GAP: In 'suggestions', give 3 specific, realistic skills the person should develop to excel in '{field}'.
5. FIELD LABEL: Set 'target_field' to exactly: "{field}"
Output ONLY valid JSON matching this exact schema (no markdown, no explanation):
{{
    @app.route("/", methods=["GET"])
def home():
    """Serves the generator dashboard."""
    return render_template("index.html")
@app.route("/generate", methods=["POST"])
def generate():
    """Handles resume upload, calls Gemini, and redirects to the rendered portfolio page."""
    if "resume" not in request.files:
        return render_template("index.html", error="No file uploaded. Please select your resume."), 400
    file = request.files["resume"]
    if file.filename == "":
        return render_template("index.html", error="No file selected."), 400
    # Validate file extension
    if not file.filename.lower().endswith(".txt"):
        return render_template("index.html", error="Only .txt files are supported."), 400
    field = request.form.get("field", "Professional").strip()
    theme = request.form.get("theme", "dark").strip().lower()
    tone = request.form.get("tone", "professional").strip().lower()
    try:
        resume_text = file.read().decode("utf-8").strip()
    except UnicodeDecodeError:
        return render_template("index.html", error="Could not read file. Make sure it's a UTF-8 encoded .txt file."), 400
    if len(resume_text) < 80:
        return render_template("index.html", error="Resume is too short. Please provide more detail."), 400
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return render_template("index.html", error="Server configuration error: GEMINI_API_KEY is not set."), 500
    client = genai.Client(api_key=api_key)
    prompt = build_prompt(resume_text, field, tone)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
         portfolio_data = json.loads(response.text)
    except json.JSONDecodeError as e:
        return render_template("index.html", error=f"AI returned malformed data. Please try again. ({e})"), 500
    except Exception as e:
        return render_template("index.html", error=f"AI generation failed: {e}"), 500
    # Select the correct template based on theme
    template_name = THEME_TEMPLATES.get(theme, "portfolio_dark.html")
    return render_template(template_name, portfolio=portfolio_data, theme=theme, tone=tone)
@app.route("/download", methods=["POST"])
def download():
    """Returns a self-contained HTML file for download."""
    try:
        portfolio_data = json.loads(request.form.get("portfolio_json", "{}"))
        theme = request.form.get("theme", "dark").lower()
        tone = request.form.get("tone", "professional").lower()
    except json.JSONDecodeError:
        return "Invalid portfolio data", 400
    template_name = THEME_TEMPLATES.get(theme, "portfolio_dark.html")
    rendered_html = render_template(template_name, portfolio=portfolio_data, theme=theme, tone=tone, standalone=True)
    response = make_response(rendered_html)
    name = portfolio_data.get("name", "portfolio").replace(" ", "_").lower()
    response.headers["Content-Disposition"] = f'attachment; filename="{name}_portfolio.html"'
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response
if __name__ == "__main__":
    app.run(debug=True)
    app.run(debug=True)

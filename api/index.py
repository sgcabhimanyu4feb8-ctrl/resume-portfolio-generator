import os
import json
from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
template_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')

app = FastAPI(title="Resume Portfolio Generator")

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=template_dir)

THEME_TEMPLATES = {
    "dark": "portfolio_dark.html",
    "light": "portfolio_light.html",
    "creative": "portfolio_creative.html",
}

def custom_url_for(request: Request):
    def _url_for(name: str, **path_params):
        if name == "static" and "filename" in path_params and "path" not in path_params:
            path_params["path"] = path_params.pop("filename")
        return str(request.url_for(name, **path_params))
    return _url_for

def render(request: Request, template_name: str, context: dict, status_code: int = 200):
    ctx = {"url_for": custom_url_for(request)}
    ctx.update(context)
    return templates.TemplateResponse(request=request, name=template_name, context=ctx, status_code=status_code)

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
  "name": "",
  "headline": "",
  "summary": "",
  "target_field": "",
  "contact": {{
    "email": "",
    "phone": "",
    "linkedin": "",
    "github": "",
    "website": ""
  }},
  "skills": [],
  "experience": [
    {{
      "role": "",
      "company": "",
      "duration": "",
      "highlights": []
    }}
  ],
  "projects": [
    {{
      "title": "",
      "description": "",
      "technologies": [],
      "link": ""
    }}
  ],
  "education": [
    {{
      "degree": "",
      "institution": "",
      "year": ""
    }}
  ],
  "certifications": [],
  "languages": [],
  "suggestions": []
}}

Resume Text:
{resume_text}
"""


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serves the generator dashboard."""
    return render(request, "index.html", {})


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    resume: UploadFile = File(None),
    field: str = Form("Professional"),
    theme: str = Form("dark"),
    tone: str = Form("professional"),
):
    """Handles resume upload, calls Gemini, and renders the generated portfolio."""
    field = field.strip() if field else "Professional"
    theme = theme.strip().lower() if theme else "dark"
    tone = tone.strip().lower() if tone else "professional"

    if not resume or not resume.filename:
        return render(request, "index.html", {"error": "No file uploaded. Please select your resume."}, status_code=400)

    if not resume.filename.lower().endswith(".txt"):
        return render(request, "index.html", {"error": "Only .txt files are supported."}, status_code=400)

    try:
        content = await resume.read()
        resume_text = content.decode("utf-8").strip()
    except UnicodeDecodeError:
        return render(request, "index.html", {"error": "Could not read file. Make sure it's a UTF-8 encoded .txt file."}, status_code=400)

    if len(resume_text) < 80:
        return render(request, "index.html", {"error": "Resume is too short. Please provide more detail."}, status_code=400)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return render(request, "index.html", {"error": "Server configuration error: GEMINI_API_KEY is not set."}, status_code=500)

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(resume_text, field, tone)

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        portfolio_data = json.loads(response.text)
    except json.JSONDecodeError as e:
        return render(request, "index.html", {"error": f"AI returned malformed data. Please try again. ({e})"}, status_code=500)
    except Exception as e:
        return render(request, "index.html", {"error": f"AI generation failed: {e}"}, status_code=500)

    template_name = THEME_TEMPLATES.get(theme, "portfolio_dark.html")
    return render(request, template_name, {"portfolio": portfolio_data, "theme": theme, "tone": tone})


@app.post("/download")
async def download(
    request: Request,
    portfolio_json: str = Form("{}"),
    theme: str = Form("dark"),
    tone: str = Form("professional"),
):
    """Returns a self-contained HTML file for download."""
    try:
        portfolio_data = json.loads(portfolio_json)
        theme = theme.lower()
        tone = tone.lower()
    except json.JSONDecodeError:
        return Response(content="Invalid portfolio data", status_code=400)

    template_name = THEME_TEMPLATES.get(theme, "portfolio_dark.html")
    template = templates.get_template(template_name)
    rendered_html = template.render(
        request=request,
        url_for=custom_url_for(request),
        portfolio=portfolio_data,
        theme=theme,
        tone=tone,
        standalone=True
    )

    name = portfolio_data.get("name", "portfolio").replace(" ", "_").lower()
    if not name:
        name = "portfolio"

    headers = {
        "Content-Disposition": f'attachment; filename="{name}_portfolio.html"',
        "Content-Type": "text/html; charset=utf-8"
    }
    return Response(content=rendered_html, headers=headers, media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("index:app", host="127.0.0.1", port=5000, reload=True)
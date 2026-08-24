import os
import json
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Set paths for templates and static assets
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
template_dir = os.path.join(base_dir, "templates")
static_dir = os.path.join(base_dir, "static")

app = FastAPI(title="Resume Portfolio Generator")
templates = Jinja2Templates(directory=template_dir)

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

# Home routes (supporting both standard and Vercel rewrite paths)
@app.get("/")
@app.get("/api/index")
async def home(request: Request):
    """Serves the generator dashboard."""
    return templates.TemplateResponse(
        request=request, 
        name="index.html"
    )

# Generate routes
@app.post("/generate")
@app.post("/api/index/generate")
@app.post("/api/generate")
async def generate(
    request: Request,
    resume: UploadFile = File(...),
    field: str = Form("Professional"),
    theme: str = Form("dark"),
    tone: str = Form("professional"),
):
    """Handles resume upload, calls Gemini, and renders the chosen portfolio template."""
    if not resume.filename.lower().endswith(".txt"):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": "Only .txt files are supported."},
            status_code=400,
        )

    try:
        content = await resume.read()
        resume_text = content.decode("utf-8").strip()
    except UnicodeDecodeError:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": "Could not read file. Make sure it is UTF-8 encoded."},
            status_code=400,
        )

    if len(resume_text) < 80:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": "Resume is too short. Please provide more detail."},
            status_code=400,
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": "Server configuration error: GEMINI_API_KEY is not set."},
            status_code=500,
        )

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(resume_text, field.strip(), tone.strip().lower())

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        portfolio_data = json.loads(response.text)
    except json.JSONDecodeError as e:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": f"AI returned malformed data. Please try again. ({e})"},
            status_code=500,
        )
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"error": f"AI generation failed: {e}"},
            status_code=500,
        )

    selected_theme = theme.strip().lower()
    template_name = THEME_TEMPLATES.get(selected_theme, "portfolio_dark.html")

    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "portfolio": portfolio_data,
            "theme": selected_theme,
            "tone": tone.strip().lower(),
        },
    )

# Download routes
@app.post("/download")
@app.post("/api/index/download")
@app.post("/api/download")
async def download(
    request: Request,
    portfolio_json: str = Form("{}"),
    theme: str = Form("dark"),
    tone: str = Form("professional"),
):
    """Returns a self-contained HTML file for download."""
    try:
        portfolio_data = json.loads(portfolio_json)
        selected_theme = theme.strip().lower()
        selected_tone = tone.strip().lower()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid portfolio data")

    template_name = THEME_TEMPLATES.get(selected_theme, "portfolio_dark.html")
    template = templates.get_template(template_name)
    rendered_html = template.render(
        portfolio=portfolio_data,
        theme=selected_theme,
        tone=selected_tone,
        standalone=True,
    )

    name = portfolio_data.get("name", "portfolio").replace(" ", "_").lower()
    headers = {
        "Content-Disposition": f'attachment; filename="{name}_portfolio.html"',
    }
    return Response(content=rendered_html, media_type="text/html; charset=utf-8", headers=headers)

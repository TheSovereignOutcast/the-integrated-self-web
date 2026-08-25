import os
import json
import base64
import requests
import swisseph as swe
import pytz
from datetime import datetime
from timezonefinder import TimezoneFinder
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import resend

app = FastAPI(title="The Integrated Self Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
resend.api_key = RESEND_API_KEY

CLAIMED_EMAILS_FILE = "claimed_emails.json"

# ----------------------------------------------------------------------
# 1. 64-Archetype Wheel Lookup & Astrological Mappings
# ----------------------------------------------------------------------
WHEEL_ORDER = [
    41, 19, 13, 49, 30, 55, 37, 63, 22, 36, 25, 17, 21, 51, 42, 3, 27, 24, 2, 23,
    8, 20, 16, 35, 45, 12, 15, 52, 39, 53, 62, 56, 31, 33, 7, 4, 29, 59, 40, 64,
    47, 6, 46, 18, 48, 57, 32, 50, 28, 44, 1, 43, 14, 34, 9, 5, 26, 11, 10, 58,
    38, 54, 61, 60
]

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

def deg_to_zodiac(deg: float) -> str:
    deg = deg % 360
    sign_idx = int(deg // 30)
    return ZODIAC_SIGNS[sign_idx]

def deg_to_archetype(deg: float) -> dict:
    deg = deg % 360
    total_segments = 64
    segment_size = 360.0 / total_segments # 5.625 deg
    
    idx = int(deg // segment_size)
    archetype_num = WHEEL_ORDER[idx]
    
    # Calculate Line (1 to 6)
    offset_in_segment = deg % segment_size
    line_size = segment_size / 6.0 # 0.9375 deg
    line_num = int(offset_in_segment // line_size) + 1
    if line_num > 6:
        line_num = 6
        
    return {"archetype": archetype_num, "line": line_num}

# ----------------------------------------------------------------------
# 2. Geocoding & Ephemeris Planetary Calculations
# ----------------------------------------------------------------------
tf = TimezoneFinder()

def get_lat_lon(location_str: str):
    url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(location_str)}&format=json&limit=1"
    headers = {"User-Agent": "TheIntegratedSelfApp/1.0"}
    res = requests.get(url, headers=headers, timeout=10)
    if not res.ok or not res.json():
        # Fallback coordinates (Greenwich)
        return 51.48, 0.0
    data = res.json()[0]
    return float(data["lat"]), float(data["lon"])

def calculate_natal_chart(date_str: str, time_str: str, location_str: str):
    lat, lon = get_lat_lon(location_str)
    tz_str = tf.timezone_at(lat=lat, lng=lon) or "UTC"
    tz = pytz.timezone(tz_str)
    
    dt_local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    dt_local = tz.localize(dt_local)
    dt_utc = dt_local.astimezone(pytz.UTC)
    
    jd = swe.julday(
        dt_utc.year, dt_utc.month, dt_utc.day,
        dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    )
    
    # Sun & Moon positions
    sun_res, _ = swe.calc_ut(jd, swe.SUN)
    sun_lon = sun_res[0]
    
    moon_res, _ = swe.calc_ut(jd, swe.MOON)
    moon_lon = moon_res[0]
    
    # Ascendant (Rising) position
    houses, ascmc = swe.houses(jd, lat, lon, b'P')
    asc_lon = ascmc[0]
    
    sun_arch = deg_to_archetype(sun_lon)
    moon_arch = deg_to_archetype(moon_lon)
    rising_arch = deg_to_archetype(asc_lon)
    
    sun_sign = deg_to_zodiac(sun_lon)
    moon_sign = deg_to_zodiac(moon_lon)
    rising_sign = deg_to_zodiac(asc_lon)
    
    return {
        "archetypes": {
            "sun": sun_arch,
            "moon": moon_arch,
            "rising": rising_arch
        },
        "signs": f"{sun_sign} Sun | {moon_sign} Moon | {rising_sign} Rising",
        "details": {
            "sun_sign": sun_sign,
            "moon_sign": moon_sign,
            "rising_sign": rising_sign
        }
    }

# ----------------------------------------------------------------------
# 3. Gemini API Narrative Synthesizer
# ----------------------------------------------------------------------
def generate_reading_narrative(name: str, struggle: str, chart_data: dict) -> str:
    if not GEMINI_API_KEY:
        return f"Archetype {chart_data['archetypes']['sun']['archetype']}: The Initiator\n\n1. THE ARCHETYPE ILLUMINATION\nYou are operating at the threshold of frequency alignment."

    sun = chart_data["archetypes"]["sun"]
    moon = chart_data["archetypes"]["moon"]
    rising = chart_data["archetypes"]["rising"]
    signs = chart_data["signs"]

    prompt = f"""
You are the master narrator and author of 'The Integrated Self' reference work.
Generate a comprehensive, resonant archetype reading for:
Name: {name}
Current Struggle/Focus: {struggle}
Core Archetype (Sun): Archetype {sun['archetype']}, Line {sun['line']}
Emotional Body (Moon): Archetype {moon['archetype']}, Line {moon['line']}
Interface (Rising): Archetype {rising['archetype']}, Line {rising['line']}
Placements: {signs}

Structure your response using these exact section headers:
1. THE ARCHETYPE ILLUMINATION: Give the official title (e.g., Archetype {sun['archetype']}: The Sovereign Pioneer) and explain the core frequency and shadow mechanics.
2. THE CURRENT DISTORTION: Address how this archetype specifically misaligns with their struggle: "{struggle}".
3. THE R.I.D. PROTOCOL:
- RECOGNIZE: Exact physical or mental cue of the distortion.
- IDENTIFY: The root belief or pattern.
- DECIDE: The precise corrective micro-action to restore frequency.
4. INTEGRATION ARCHITECTURE: A closing synthesis of how their Moon and Rising work in synergy with this Sun archetype.

Maintain an elevated, grounded, authoritative tone. Do not use generic horoscopic fluff.
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1400}
    }
    
    res = requests.post(url, json=payload, timeout=60)
    if res.ok:
        data = res.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            pass
    return f"Archetype {sun['archetype']}: The Sovereign Path\n\n1. THE ARCHETYPE ILLUMINATION\nYour frequency coordinate is fully registered."

# ----------------------------------------------------------------------
# 4. ReportLab PDF Generation Engine
# ----------------------------------------------------------------------
def build_pdf_document(name: str, chart_data: dict, narrative_text: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40, leftMargin=40,
        topMargin=40, bottomMargin=40
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#111A38'),
        spaceAfter=12
    )
    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#8992B4'),
        spaceAfter=18
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor('#080D1C'),
        spaceAfter=10
    )
    section_style = ParagraphStyle(
        'DocSec',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#C9922B'),
        spaceBefore=14,
        spaceAfter=6
    )

    story = []
    story.append(Paragraph(f"THE INTEGRATED SELF: PERSONAL FREQUENCY BLUEPRINT", title_style))
    story.append(Paragraph(f"Prepared for: <b>{name}</b> &nbsp;|&nbsp; Placements: {chart_data['signs']}", meta_style))
    story.append(Spacer(1, 10))

    lines = narrative_text.split('\n')
    for line in lines:
        clean = line.strip()
        if not clean:
            continue
        if any(clean.startswith(f"{i}.") for i in range(1, 10)):
            story.append(Paragraph(clean, section_style))
        else:
            story.append(Paragraph(clean, body_style))

    doc.build(story)
    pdf_val = buffer.getvalue()
    buffer.close()
    return pdf_val

# ----------------------------------------------------------------------
# 5. Email Deduplication & Delivery Systems
# ----------------------------------------------------------------------
def is_email_claimed(email: str) -> bool:
    if not os.path.exists(CLAIMED_EMAILS_FILE):
        return False
    try:
        with open(CLAIMED_EMAILS_FILE, "r") as f:
            claimed = set(json.load(f))
            return email.lower().strip() in claimed
    except Exception:
        return False

def record_email(email: str):
    claimed = set()
    if os.path.exists(CLAIMED_EMAILS_FILE):
        try:
            with open(CLAIMED_EMAILS_FILE, "r") as f:
                claimed = set(json.load(f))
        except Exception:
            pass
    claimed.add(email.lower().strip())
    with open(CLAIMED_EMAILS_FILE, "w") as f:
        json.dump(list(claimed), f)

def send_reading_email(to_email: str, name: str, pdf_bytes: bytes, archetype_num: int, archetype_name: str):
    if not resend.api_key:
        print("RESEND_API_KEY not set. Email delivery skipped.")
        return

    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8") if pdf_bytes else None

    email_payload = {
        "from": "The Integrated Self <readings@thesovereignoutcast.com>",
        "to": [to_email.strip()],
        "subject": f"Your Reading: Archetype {archetype_num} — {archetype_name}",
        "html": f"""
        <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; color: #111A38; line-height: 1.6;">
            <h2 style="font-weight: normal; color: #111A38;">Greetings {name},</h2>
            <p>Your birth coordinate calculation is complete. Attached to this email is your full complimentary reading for <strong>Archetype {archetype_num}: {archetype_name}</strong>.</p>
            <p>Ready to unlock all 64 coordinates and dive into the complete manual?</p>
            <p><a href="https://gumroad.com" style="display:inline-block; padding: 12px 20px; background-color: #C9922B; color: #080D1C; text-decoration: none; font-weight: bold; border-radius: 2px;">Explore The Master Reference Book</a></p>
            <br>
            <p style="color: #8992B4; font-size: 13px;">The Integrated Self · Sol Santos</p>
        </div>
        """
    }

    if encoded_pdf:
        email_payload["attachments"] = [
            {
                "filename": f"Archetype_{archetype_num}_Reading.pdf",
                "content": encoded_pdf,
            }
        ]

    try:
        resend.Emails.send(email_payload)
    except Exception as e:
        print(f"Resend Dispatch Error: {e}")

# ----------------------------------------------------------------------
# 6. Request Model & Endpoint Routing
# ----------------------------------------------------------------------
class FreeSnapshotRequest(BaseModel):
    name: str
    email: str
    date: str
    time: str
    location: str
    struggle: str = "finding alignment"

@app.post("/free-snapshot")
async def free_snapshot(req: FreeSnapshotRequest, key: str = None):
    if key != "sovereign16" and is_email_claimed(req.email):
        raise HTTPException(
            status_code=403,
            detail="You have already claimed your complimentary reading. Explore all 64 archetypes in The Master Reference Book."
        )

    # 1. Ephemeris & Chart Calculation
    chart_data = calculate_natal_chart(req.date, req.time, req.location)
    
    # 2. Gemini Narrative Synthesis
    snapshot_text = generate_reading_narrative(req.name, req.struggle, chart_data)
    
    # 3. PDF Compilation
    pdf_bytes = build_pdf_document(req.name, chart_data, snapshot_text)
    
    # 4. Extract Archetype Label & Email PDF
    sun = chart_data["archetypes"]["sun"]
    name_match = (snapshot_text.split('\n')[0].replace("Archetype", "").strip())
    label = f"Archetype {sun['archetype']}" if not name_match else snapshot_text.split('\n')[0]
    
    send_reading_email(req.email, req.name, pdf_bytes, sun["archetype"], label)

    # 5. Lock Free Tier for Email
    if key != "sovereign16":
        record_email(req.email)

    return {
        "archetypes": chart_data["archetypes"],
        "signs": chart_data["signs"],
        "snapshot": snapshot_text
    }
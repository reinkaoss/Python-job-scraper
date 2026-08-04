"""
End-to-end test of the File Extractor backend with OpenAI mocked.

Verifies:
1. docx text extraction + GPT splitting (mocked split response) → 4 UBS jobs
2. pdf and txt extraction
3. /api/extract-file-job returns job_details (mocked extraction response)
4. /api/encode-job-urls → /api/job-page round trip renders every field
5. Error paths: unsupported type, empty text, bad token
"""
import io
import json
import os
import sys
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Build a synthetic multi-job docx (4 postings), so the test is self-contained.
# Pass a path to a real .docx as the first CLI argument to use that instead:
#   python test_extractor.py path/to/file.docx
JOB_HEADINGS = [
    "2027 Apprenticeship – Group Technology Office (GTO) – London",
    "2027 Apprenticeship – Global Wealth Management – London",
    "2027 Apprenticeship – Global Markets – London",
    "2027 Apprenticeship – Investment Bank Chief Operating Office – London",
]
JOB_BODIES = [
    "Your role: design, develop and improve digital products for the Group Technology Office. " * 30,
    "Your team: the Global Wealth Management team in London serving high-net worth clients. " * 30,
    "Your role: experience how we help clients buy and sell financial instruments. " * 30,
    "Your team: the Investment Bank Chief Operating Office shaping the bank's future. " * 30,
]

def build_synthetic_docx():
    def para(text):
        return f"<w:p><w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"
    body = "".join(para(h) + para(b) for h, b in zip(JOB_HEADINGS, JOB_BODIES))
    document = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml",
                   "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                   "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                   "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
                   "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
                   "</Types>")
        z.writestr("word/document.xml", document)
    return buf.getvalue()

if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
    with open(sys.argv[1], "rb") as fh:
        DOCX_BYTES = fh.read()
    print(f"Using real docx: {sys.argv[1]}")
else:
    DOCX_BYTES = build_synthetic_docx()

# ── Mock OpenAI before importing the app ─────────────────────────────────────
import openai

SPLIT_RESPONSE = {
    "jobs": [{"title": h, "start_marker": h} for h in JOB_HEADINGS]
}

EXTRACT_RESPONSE = {
    "title": "Group Technology Office Apprenticeship 2027",
    "company": "UBS",
    "location": "London",
    "salary_type": "Competitive",
    "salary_amount": None,
    "salary_frequency": None,
    "salary_perks": "Flexible working options",
    "job_type": "Degree Apprenticeship",
    "description": "<h2>Your role</h2><p>Interested in working in finance?</p><h2>You'll get to</h2><li>design, develop and improve digital products</li><li>provide transparency across data quality</li><h2>About the Company</h2><p>UBS is the world's largest wealth manager.</p>",
    "apply_link": "null - this job came from an uploaded file",
    "application_deadline": None,
    "relevant_year": "School leaver",
    "job_tags": ["Information Technology", "Banking"],
    "employment_start_date": "01/09/2027",
}

def fake_chat_completion_create(model=None, messages=None, **kwargs):
    prompt = messages[0]["content"]
    if "start_marker" in prompt:  # split prompt
        content = "```json\n" + json.dumps(SPLIT_RESPONSE) + "\n```"  # fence on purpose
    else:  # extraction prompt
        content = json.dumps(EXTRACT_RESPONSE)
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 123}}

openai.ChatCompletion.create = fake_chat_completion_create

from api.index import app  # noqa: E402

failures = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)

client = app.test_client()

# ── 1. Upload a multi-job docx ───────────────────────────────────────────────
docx_bytes = DOCX_BYTES

resp = client.post("/api/extract-file",
                   data={"file": (io.BytesIO(docx_bytes), "2027_Apprenticeships_JD 1.docx")},
                   content_type="multipart/form-data")
payload = resp.get_json()
check("extract-file returns 200", resp.status_code == 200, str(payload))
jobs = payload.get("jobs", [])
check("docx split into 4 jobs", len(jobs) == 4, f"got {len(jobs)}")
check("filename echoed", payload.get("filename") == "2027_Apprenticeships_JD 1.docx")
if len(jobs) == 4:
    check("chunk 1 contains GTO content", "Group Technology Office" in jobs[0]["text"])
    check("chunk 2 contains GWM content", "Global Wealth Management" in jobs[1]["text"])
    check("chunk 3 contains Global Markets content", "buy and sell financial" in jobs[2]["text"])
    check("chunk 4 contains IB COO content", "Chief Operating Office" in jobs[3]["text"])
    check("chunks don't leak into each other",
          "Global Wealth Management team in London" not in jobs[0]["text"])
    total_len = sum(len(j["text"]) for j in jobs)
    check("chunks cover most of the document", total_len > 8000, f"total {total_len}")

# ── 2. txt upload ────────────────────────────────────────────────────────────
resp = client.post("/api/extract-file",
                   data={"file": (io.BytesIO("Software Engineer\nGreat job in Leeds".encode()), "job.txt")},
                   content_type="multipart/form-data")
check("txt upload works", resp.status_code == 200 and len(resp.get_json()["jobs"]) >= 1)

# ── 3. pdf upload (generate a small pdf on the fly) ──────────────────────────
try:
    from reportlab.pdfgen import canvas  # noqa
    have_reportlab = True
except ImportError:
    have_reportlab = False

if have_reportlab:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "Marketing Assistant Apprenticeship 2027")
    c.drawString(72, 700, "Company: Acme Ltd. Location: Manchester. Salary: £22,000 per annum.")
    c.save()
    resp = client.post("/api/extract-file",
                       data={"file": (io.BytesIO(buf.getvalue()), "job.pdf")},
                       content_type="multipart/form-data")
    p = resp.get_json()
    check("pdf upload works", resp.status_code == 200, str(p))
    check("pdf text extracted", "Marketing Assistant" in p["jobs"][0]["text"] if resp.status_code == 200 else False)

# ── 4. Unsupported / broken files ────────────────────────────────────────────
resp = client.post("/api/extract-file",
                   data={"file": (io.BytesIO(b"binary"), "cv.pages")},
                   content_type="multipart/form-data")
check("unsupported extension → 400", resp.status_code == 400 and "Unsupported" in resp.get_json()["error"])

resp = client.post("/api/extract-file",
                   data={"file": (io.BytesIO(b"not a real docx"), "fake.docx")},
                   content_type="multipart/form-data")
check("corrupt docx → 400 with friendly error", resp.status_code == 400, str(resp.get_json()))

# empty docx (valid zip, no text)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("word/document.xml", "<?xml version='1.0'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body></w:body></w:document>")
resp = client.post("/api/extract-file",
                   data={"file": (io.BytesIO(buf.getvalue()), "empty.docx")},
                   content_type="multipart/form-data")
check("empty docx → 400 'no text'", resp.status_code == 400 and "No text" in resp.get_json()["error"])

resp = client.post("/api/extract-file", data={}, content_type="multipart/form-data")
check("missing file → 400", resp.status_code == 400)

# ── 5. Per-job extraction ────────────────────────────────────────────────────
resp = client.post("/api/extract-file-job", json={"text": jobs[0]["text"], "source": "2027_Apprenticeships_JD 1.docx"})
payload = resp.get_json()
check("extract-file-job returns 200", resp.status_code == 200, str(payload))
jd = payload.get("job_details", {})
check("job_details has title", jd.get("title") == EXTRACT_RESPONSE["title"])
check("apply_link forced to null for file jobs", jd.get("apply_link") is None)
check("source echoed", payload.get("source") == "2027_Apprenticeships_JD 1.docx")

resp = client.post("/api/extract-file-job", json={"text": ""})
check("empty text → 400", resp.status_code == 400)

# ── 6. URL encode → job-page round trip ──────────────────────────────────────
amended = dict(jd)
amended["apply_link"] = "https://www.ubs.com/careers/apply/12345"
amended["application_deadline"] = "15/01/2027"

resp = client.post("/api/encode-job-urls", json={"jobs": [amended], "base_url": "https://job-scraper.example.com/"})
payload = resp.get_json()
check("encode-job-urls returns 200", resp.status_code == 200, str(payload))
row = payload["urls"][0]
check("url uses base domain", row["url"].startswith("https://job-scraper.example.com/api/job-page?d="))
check("url length reported", row["length"] == len(row["url"]))
print(f"       generated URL length: {row['length']} chars")

token = row["url"].split("?d=")[1]
resp = client.get(f"/api/job-page?d={token}")
html = resp.get_data(as_text=True)
check("job-page returns 200 html", resp.status_code == 200 and resp.mimetype == "text/html")
for needle in [
    "Group Technology Office Apprenticeship 2027",   # title
    "Company:", "UBS",
    "Location:", "London",
    "Job Type:", "Degree Apprenticeship",
    "Salary Type:", "Competitive",
    "Perks &amp; Benefits:", "Flexible working options",
    "Application Deadline:", "15/01/2027",
    "Employment Start Date:", "01/09/2027",
    "Relevant Year:", "School leaver",
    "Information Technology, Banking",
    "https://www.ubs.com/careers/apply/12345",
    "<h2>Your role</h2>",
    "design, develop and improve digital products",
]:
    check(f"job-page contains {needle[:40]!r}", needle in html)

# get_text() sanity: what the consuming scraper's soup.get_text() would see
from bs4 import BeautifulSoup
text = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
check("soup.get_text has labelled company line", "Company:\nUBS" in text or "Company: UBS" in text)

# ── 7. Sanitiser strips scripts ──────────────────────────────────────────────
evil = dict(amended)
evil["description"] = '<p>ok</p><script>alert(1)</script><p onclick="x()">click</p><a href="javascript:evil()">bad</a><a href="https://good.com">good</a>'
resp = client.post("/api/encode-job-urls", json={"jobs": [evil], "base_url": "https://x.example.com"})
token = resp.get_json()["urls"][0]["url"].split("?d=")[1]
html = client.get(f"/api/job-page?d={token}").get_data(as_text=True)
check("script tag stripped", "<script>" not in html and "alert(1)" not in html)
check("onclick stripped", "onclick" not in html)
check("javascript: href stripped", "javascript:evil" not in html)
check("https href kept", 'href="https://good.com"' in html)

# ── 8. Bad tokens ────────────────────────────────────────────────────────────
check("missing token → 400", client.get("/api/job-page").status_code == 400)
check("garbage token → 400", client.get("/api/job-page?d=garbage!!").status_code == 400)

# ── 9. Unicode round trip (£, é, –) ─────────────────────────────────────────
uni = dict(amended); uni["salary_amount"] = "£25,000 – £30,000"; uni["company"] = "Café Sté"
resp = client.post("/api/encode-job-urls", json={"jobs": [uni], "base_url": "https://x.example.com"})
token = resp.get_json()["urls"][0]["url"].split("?d=")[1]
html = client.get(f"/api/job-page?d={token}").get_data(as_text=True)
check("unicode survives round trip", "£25,000 – £30,000" in html and "Café Sté" in html)

# ── 9b. Missing server dependency → clear, actionable error ─────────────────
with mock.patch.dict(sys.modules, {"docx2txt": None}):
    resp = client.post("/api/extract-file",
                       data={"file": (io.BytesIO(docx_bytes), "jd.docx")},
                       content_type="multipart/form-data")
    err = (resp.get_json() or {}).get("error", "")
    check("missing docx2txt → names the dependency",
          resp.status_code == 400 and "docx2txt" in err and "requirements.txt" in err, err)

with mock.patch.dict(sys.modules, {"pdfminer.high_level": None, "pdfminer": None}):
    resp = client.post("/api/extract-file",
                       data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "jd.pdf")},
                       content_type="multipart/form-data")
    err = (resp.get_json() or {}).get("error", "")
    check("missing pdfminer → names the dependency",
          resp.status_code == 400 and "pdfminer" in err and "requirements.txt" in err, err)

# ── 10. Split fallback when GPT fails ────────────────────────────────────────
def broken_create(**kwargs):
    raise RuntimeError("API down")
with mock.patch.object(openai.ChatCompletion, "create", side_effect=broken_create):
    resp = client.post("/api/extract-file",
                       data={"file": (io.BytesIO(docx_bytes), "jd.docx")},
                       content_type="multipart/form-data")
    p = resp.get_json()
    check("split falls back to single job when GPT fails",
          resp.status_code == 200 and len(p["jobs"]) == 1 and "Group Technology Office" in p["jobs"][0]["text"])

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")

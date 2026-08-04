import io
import json
import logging
import re
import sys

import openai

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

SUPPORTED_EXTENSIONS = {"docx", "pdf", "txt", "md", "text"}

# Keep uploads comfortably inside Vercel's 4.5MB request body limit
MAX_FILE_BYTES = 4 * 1024 * 1024
# Cap the amount of text sent to the split prompt
MAX_SPLIT_CHARS = 120_000


def get_file_extension(filename):
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def extract_text_from_upload(data, filename):
    """Extract plain text from an uploaded file (docx, pdf, txt, md)."""
    ext = get_file_extension(filename)

    if ext not in SUPPORTED_EXTENSIONS:
        if ext == "doc":
            raise ValueError(
                "Legacy .doc files are not supported. Please re-save the file as .docx and try again."
            )
        raise ValueError(
            f"Unsupported file type '.{ext}'. Supported types: .docx, .pdf, .txt, .md"
        )

    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File is too large (max 4MB).")

    if ext == "docx":
        try:
            import docx2txt
        except ImportError:
            raise ValueError(
                "Server dependency missing: docx2txt. Run 'pip install -r requirements.txt' "
                "in the environment that runs the Flask API (e.g. '.venv/bin/pip install -r requirements.txt') "
                "and restart the backend."
            )
        try:
            text = docx2txt.process(io.BytesIO(data))
        except Exception as e:
            logger.error(f"Failed to read docx '{filename}': {e}")
            raise ValueError(f"Could not read this .docx file ({e}). Is it a valid Word document?")
    elif ext == "pdf":
        try:
            from pdfminer.high_level import extract_text as pdf_extract_text
        except ImportError:
            raise ValueError(
                "Server dependency missing: pdfminer.six. Run 'pip install -r requirements.txt' "
                "in the environment that runs the Flask API (e.g. '.venv/bin/pip install -r requirements.txt') "
                "and restart the backend."
            )
        try:
            text = pdf_extract_text(io.BytesIO(data))
        except Exception as e:
            logger.error(f"Failed to read pdf '{filename}': {e}")
            raise ValueError(f"Could not read this PDF file ({e}). Is it a valid, unencrypted PDF?")
    else:  # txt / md / text
        text = data.decode("utf-8", errors="replace")

    text = normalise_text(text)
    if not text.strip():
        raise ValueError(
            "No text could be extracted from this file. If it is a scanned PDF (images of text), "
            "please run OCR on it first or paste the text into a .txt file."
        )
    return text


def normalise_text(text):
    """Collapse excessive blank lines / whitespace but keep line structure (needed for splitting)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_model_json(content):
    """Parse JSON from a model response, tolerating markdown code fences."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content.strip())
    return json.loads(content.strip())


def split_jobs_from_text(text, filename=""):
    """
    Split a document's text into individual job postings.

    Returns a list of {"title": str|None, "text": str} chunks (one per posting).
    Falls back to treating the whole document as a single job if splitting
    fails for any reason.
    """
    fallback = [{"title": None, "text": text}]
    clipped = text[:MAX_SPLIT_CHARS]

    prompt = f"""
You are given the plain text of a document (extracted from a file named "{filename}").
The document contains ONE or MORE job postings.

Identify every distinct job posting in the document, in order of appearance.

Return STRICT JSON only (no commentary, no markdown), with this shape:
{{"jobs": [{{"title": "<job posting title>", "start_marker": "<the EXACT text of the first line of that posting, copied VERBATIM from the document>"}}]}}

Rules:
- "start_marker" must be an exact, verbatim substring of the document (typically the posting's heading line). Do not paraphrase, trim words, or fix punctuation.
- Each posting starts at its marker and ends where the next posting's marker begins (the last one runs to the end of the document).
- Repeated boilerplate (e.g. "About us", disclaimers) belongs to the posting it appears under - do NOT treat it as a separate job.
- If the document contains only one job posting, return a single entry.

Document text:
{clipped}
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2048,
            top_p=1,
        )
        parsed = _parse_model_json(response["choices"][0]["message"]["content"])
        markers = parsed.get("jobs", [])
    except Exception as e:
        logger.error(f"Job splitting failed for '{filename}', treating file as one job: {e}")
        return fallback

    if not isinstance(markers, list) or len(markers) == 0:
        return fallback

    # Locate each marker in the original text
    positions = []
    search_from = 0
    for m in markers:
        marker = (m.get("start_marker") or "").strip()
        if not marker:
            continue
        idx = text.find(marker, search_from)
        if idx == -1:
            # Retry from the beginning in case the model reordered slightly
            idx = text.find(marker)
        if idx == -1:
            logger.warning(f"Split marker not found in text: {marker[:80]!r}")
            continue
        positions.append({"title": m.get("title"), "start": idx})
        search_from = idx + len(marker)

    if len(positions) == 0:
        return fallback

    positions.sort(key=lambda p: p["start"])

    chunks = []
    for i, pos in enumerate(positions):
        start = pos["start"] if i > 0 else 0  # include any preamble in the first chunk
        end = positions[i + 1]["start"] if i + 1 < len(positions) else len(text)
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"title": pos["title"], "text": chunk_text})

    return chunks if chunks else fallback

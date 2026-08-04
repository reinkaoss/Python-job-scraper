from flask import Flask, Blueprint, request, jsonify, Response
from flask_cors import CORS
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from scripts.fetch_jobs import extract_job_details, save_page_source
from scripts.extract_from_file import extract_text_from_upload, split_jobs_from_text
import base64
import html as html_lib
import json
import os
import zlib
from time import time
import sys

# Set up basic logging with a StreamHandler so logs go to stdout
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
_handler = logging.StreamHandler(sys.stdout)  # renamed from handler to _handler
_handler.setLevel(logging.DEBUG)
logger.addHandler(_handler)

# Load environment variables
load_dotenv()

# Define file paths based on environment
folderPrefix = '/tmp' if os.getenv("APP_ENV") == 'production' else './data'
JOB_DETAILS_FILE = f"{folderPrefix}/job_details.json"

# Create a Flask app and enable CORS
app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

# Create a Blueprint
fetch_jobs_blueprint = Blueprint('fetch_jobs', __name__)

@app.route('/')
def home():
    return 'Testing this works'

# Route to scrape a single URL (unchanged)
@fetch_jobs_blueprint.route('/scrape-url', methods=['POST'])
def scrape_url():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        file_name = "saved_page.html"
        file_path = save_page_source(url, file_name)
        logger.debug(f"File path after saving: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        all_text = soup.get_text(separator="\n", strip=True)

        job_details = extract_job_details(all_text, url)
        if job_details:
            os.makedirs(os.path.dirname(JOB_DETAILS_FILE), exist_ok=True)
            with open(JOB_DETAILS_FILE, "w", encoding="utf-8") as f:
                json.dump(job_details, f, indent=4)
            return jsonify(job_details)
        else:
            return jsonify({"error": "Failed to extract job details"}), 500
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# Route to scrape multiple URLs in batches (batch parameters expected from client)
@fetch_jobs_blueprint.route('/scrape-multiple', methods=['POST'])
def scrape_multiple():
    data = request.json
    urls = data.get("urls")
    if not urls or not isinstance(urls, list):
        return jsonify({"error": "A list of URLs is required"}), 400

    batch_index = data.get("batch", 0)
    batch_size = data.get("batch_size", 1)
    batch_urls = urls[batch_index * batch_size: (batch_index + 1) * batch_size]
    results = []
    batch_start = time()
    logger.info(f"Starting batch {batch_index} with {len(batch_urls)} URLs.")

    try:
        for idx, url in enumerate(batch_urls):
            file_name = f"saved_page_{batch_index}_{idx}.html"
            try:
                file_path = save_page_source(url, file_name)
            except Exception as e:
                logger.error(f"Error saving page for URL {url}: {e}")
                results.append({"url": url, "error": "Failed to load page"})
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            soup = BeautifulSoup(html_content, 'html.parser')
            all_text = soup.get_text(separator="\n", strip=True)
            job_details = extract_job_details(all_text, url)
            if job_details:
                results.append({"url": url, "job_details": job_details})
            else:
                results.append({"url": url, "error": "Failed to extract job details"})

        batch_end = time()
        logger.info(f"Batch {batch_index} processed in {batch_end - batch_start:.2f} seconds.")

        if os.path.exists(JOB_DETAILS_FILE):
            with open(JOB_DETAILS_FILE, 'r', encoding='utf-8') as f:
                all_results = json.load(f)
            if not isinstance(all_results, list):
                all_results = [all_results]
        else:
            all_results = []
        all_results.extend(results)
        with open(JOB_DETAILS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=4)
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error in batch {batch_index}: {e}")
        return jsonify({"error": str(e)}), 500

# ─── File Extractor: upload a file, split it into job postings ──────────────

# Route to extract text from an uploaded file and split it into individual jobs
@fetch_jobs_blueprint.route('/extract-file', methods=['POST'])
def extract_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded. Send the file as multipart form field 'file'."}), 400

    uploaded = request.files['file']
    filename = uploaded.filename or 'upload'

    try:
        text = extract_text_from_upload(uploaded.read(), filename)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {e}")
        return jsonify({"error": f"Failed to read file: {e}"}), 500

    try:
        chunks = split_jobs_from_text(text, filename)
        return jsonify({"filename": filename, "jobs": chunks})
    except Exception as e:
        logger.error(f"Error splitting jobs from {filename}: {e}")
        # Fall back to a single chunk rather than failing outright
        return jsonify({"filename": filename, "jobs": [{"title": None, "text": text}]})

# Route to run the structured extraction on one job's text (mirrors the per-URL pattern
# so each request stays within serverless time limits; the client loops over chunks)
@fetch_jobs_blueprint.route('/extract-file-job', methods=['POST'])
def extract_file_job():
    data = request.json or {}
    text = data.get("text")
    source = data.get("source", "uploaded file")
    if not text or not text.strip():
        return jsonify({"error": "Field 'text' is required"}), 400

    try:
        job_details = extract_job_details(
            text,
            "null - this job came from an uploaded file, so no apply link is available; set apply_link to null"
        )
        if job_details:
            # The prompt above makes the model echo instructions into apply_link; force it clean
            # so the moderator fills in the real link by hand.
            job_details["apply_link"] = None
            return jsonify({"source": source, "job_details": job_details})
        return jsonify({"error": "Failed to extract job details"}), 500
    except Exception as e:
        logger.error(f"Error extracting job from {source}: {e}")
        return jsonify({"error": str(e)}), 500

# ─── Self-contained job URLs: encode amended data into a scrapeable page URL ─

URL_LENGTH_WARNING = 8000  # warn above this; most fetchers/proxies accept well beyond it

def _encode_job_data(job_details):
    payload = json.dumps(job_details, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return base64.urlsafe_b64encode(zlib.compress(payload, 9)).decode('ascii').rstrip('=')

def _decode_job_data(token):
    token = token.strip()
    padding = '=' * (-len(token) % 4)
    payload = zlib.decompress(base64.urlsafe_b64decode(token + padding))
    return json.loads(payload.decode('utf-8'))

ALLOWED_DESCRIPTION_TAGS = {'h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'li',
                            'strong', 'b', 'em', 'i', 'u', 'br', 'a', 'span', 'div'}

def _sanitise_description_html(raw_html):
    """Keep only harmless formatting tags; strip scripts/styles/event handlers."""
    soup = BeautifulSoup(raw_html or '', 'html.parser')
    for tag in soup.find_all(True):
        if tag.name in ('script', 'style', 'iframe', 'object', 'embed', 'link', 'meta'):
            tag.decompose()
            continue
        if tag.name not in ALLOWED_DESCRIPTION_TAGS:
            tag.unwrap()
            continue
        href = tag.get('href') if tag.name == 'a' else None
        tag.attrs = {}
        if href and href.lower().startswith(('http://', 'https://', 'mailto:')):
            tag['href'] = href
    return str(soup)

def _job_page_field(label, value):
    if value in (None, '', 'null', 'None', []):
        return ''
    if isinstance(value, (list, tuple)):
        value = ', '.join(str(v) for v in value)
    return (
        f'<div class="meta-row"><span class="meta-label">{html_lib.escape(label)}:</span> '
        f'<span class="meta-value">{html_lib.escape(str(value))}</span></div>'
    )

def render_job_page(jd):
    title = jd.get('title') or 'Job Listing'
    start_date = jd.get('employment_start_date') or jd.get('Employment Start Date')
    apply_link = jd.get('apply_link')

    meta_rows = ''.join([
        _job_page_field('Company', jd.get('company')),
        _job_page_field('Location', jd.get('location')),
        _job_page_field('Job Type', jd.get('job_type')),
        _job_page_field('Salary Type', jd.get('salary_type')),
        _job_page_field('Salary Amount', jd.get('salary_amount')),
        _job_page_field('Salary Frequency', jd.get('salary_frequency')),
        _job_page_field('Perks & Benefits', jd.get('salary_perks')),
        _job_page_field('Application Deadline', jd.get('application_deadline')),
        _job_page_field('Employment Start Date', start_date),
        _job_page_field('Relevant Year', jd.get('relevant_year')),
        _job_page_field('Tags', jd.get('job_tags')),
    ])

    apply_row = ''
    if apply_link and apply_link not in ('null', 'None'):
        safe_link = html_lib.escape(apply_link)
        apply_row = (
            f'<div class="meta-row"><span class="meta-label">Apply Link:</span> '
            f'<span class="meta-value"><a href="{safe_link}">{safe_link}</a></span></div>'
        )

    description_html = _sanitise_description_html(jd.get('description') or '')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="Higherin Job Extractor">
<title>{html_lib.escape(title)}</title>
<style>
  body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; color: hsl(240,8%,25%);
         background: hsl(240,20%,99%); margin: 0; padding: 2rem 1rem; line-height: 1.6; }}
  .job-page {{ max-width: 760px; margin: 0 auto; background: #fff; border: 1px solid hsl(240,12%,90%);
               border-radius: 14px; padding: 2rem 2.25rem 2.5rem; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 1rem; }}
  h2 {{ font-size: 1.15rem; margin: 1.5rem 0 0.5rem; }}
  h3 {{ font-size: 1rem; margin: 1.25rem 0 0.4rem; }}
  .meta {{ border: 1px solid hsl(240,12%,90%); background: hsl(245,56%,97%);
           border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; }}
  .meta-row {{ margin: 0.2rem 0; font-size: 0.95rem; }}
  .meta-label {{ font-weight: 700; }}
  li {{ margin: 0.25rem 0; }}
  a {{ color: hsl(245,56%,50%); word-break: break-all; }}
</style>
</head>
<body>
<article class="job-page">
<h1>{html_lib.escape(title)}</h1>
<section class="meta">
{meta_rows}{apply_row}
</section>
<section class="job-description">
{description_html}
</section>
</article>
</body>
</html>"""

# Route to turn amended job data into self-contained URLs (data travels inside the URL)
@fetch_jobs_blueprint.route('/encode-job-urls', methods=['POST'])
def encode_job_urls():
    data = request.json or {}
    jobs = data.get("jobs")
    if not jobs or not isinstance(jobs, list):
        return jsonify({"error": "A list of job objects is required in 'jobs'"}), 400

    base_url = (data.get("base_url") or request.host_url or '').strip().rstrip('/')
    if not base_url.lower().startswith(('http://', 'https://')):
        return jsonify({"error": f"Invalid base_url: {base_url}"}), 400

    results = []
    for jd in jobs:
        try:
            token = _encode_job_data(jd)
            url = f"{base_url}/api/job-page?d={token}"
            results.append({
                "title": (jd or {}).get("title"),
                "url": url,
                "length": len(url),
                "too_long": len(url) > URL_LENGTH_WARNING,
            })
        except Exception as e:
            logger.error(f"Error encoding job URL: {e}")
            results.append({"title": (jd or {}).get("title"), "error": str(e)})
    return jsonify({"urls": results})

# Route that serves the self-contained job page (what the other scraper fetches)
@fetch_jobs_blueprint.route('/job-page', methods=['GET'])
def job_page():
    token = request.args.get('d')
    if not token:
        return Response("<h1>Missing job data</h1><p>Expected a 'd' query parameter.</p>",
                        status=400, mimetype='text/html')
    try:
        jd = _decode_job_data(token)
    except Exception as e:
        logger.error(f"Failed to decode job page token: {e}")
        return Response("<h1>Invalid job data</h1><p>This job URL could not be decoded.</p>",
                        status=400, mimetype='text/html')
    return Response(render_job_page(jd), mimetype='text/html')

app.register_blueprint(fetch_jobs_blueprint, url_prefix='/api')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, port=port)

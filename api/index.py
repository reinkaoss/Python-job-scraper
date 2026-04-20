from flask import Flask, Blueprint, request, jsonify
from flask_cors import CORS
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from scripts.fetch_jobs import extract_job_details, save_page_source
import json
import os
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

app.register_blueprint(fetch_jobs_blueprint, url_prefix='/api')

if __name__ == '__main__':
    app.run(debug=True)

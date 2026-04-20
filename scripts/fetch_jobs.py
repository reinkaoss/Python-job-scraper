import os
import json
import requests
import openai
import logging
from dotenv import load_dotenv
import sys

# Set up logging
logging.getLogger('openai').setLevel(logging.WARNING)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
PHANTOMJSCLOUD_API_KEY = os.getenv("PHANTOMJSCLOUD_API_KEY")
folderPrefix = '/tmp' if os.getenv("APP_ENV") == 'production' else './data'

# Define persistent output file
JOB_DETAILS_FILE = f"{folderPrefix}/job_details.json"
os.makedirs(folderPrefix, exist_ok=True)

def save_page_source(url, file_name):
    saved_pages_dir = os.path.join(folderPrefix, "saved_pages")
    logger.debug(f"Saved pages directory: {saved_pages_dir}")
    os.makedirs(saved_pages_dir, exist_ok=True)
    full_path = os.path.join(os.getcwd(), saved_pages_dir, file_name)
    logger.debug(f"Saving page to: {full_path}")

    payload = {
        "url": url,
        "renderType": "html",
        "timeout": 30000,  # in milliseconds
        "loadImages": False,
        "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    }

    try:
        response = requests.post(
            f"https://phantomjscloud.com/api/browser/v2/{PHANTOMJSCLOUD_API_KEY}/",
            json=payload,
            timeout=60  # seconds
        )
        if response.status_code == 200:
            html_content = response.text
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.debug(f"Page saved successfully to {full_path}")
            return full_path
        else:
            logger.error(f"PhantomJSCloud API error: {response.status_code} - {response.text}")
            raise Exception(f"PhantomJSCloud API error: {response.status_code}")
    except Exception as e:
        logger.error(f"Error while saving page with PhantomJSCloud: {e}")
        raise

TAGS_LIST = """
Accounting
Business Operations
Architecture
Banking
Property Development
Customer Service
Teaching
Electronic and Electrical Engineering
Engineering
Hospitality Management
Government
Information Technology
Construction
Medicine
Human Resources
Journalism & Publishing
Legal/Law
Logistics and Operations
Management Consulting
Manufacturing
Marketing
Market Research
Pharmaceutical
Retail Manager
Sales
Science
Social Work
Automotive Engineering
Business Management
PR and Communications
Insurance and Risk Management
Actuary
Audit
Advertising
Television/Film/Media
Investment Banking
Retail Banking
Commercial Banking
Data Analysis
Property Management
Computer Science
Consumer Products/FMCG
Bar and Waiting
Environmental Science
Aeronautical & Aerospace Engineering
Civil Engineering
Chemical Engineering
Computer Systems Engineering
Mechanical Engineering
Material & Mineral Engineering
Finance
Graphic Design
Purchasing and Supply
Recruitment
Surveying
Voluntary
Armed Forces
Product Design
Fashion Design
Prison Officer
Chemistry
Economics
Supply Chain Management
Transport Planning
Driver
Police Officer
Firefighter
Plumbing
Electrician
Carpentry
Healthcare
Catering
Cyber Security
Merchandising
Artificial Intelligence (AI)
Sustainability
Employment Law
Corporate Law
Intellectual Property Law
Commercial Law
Digital Marketing
Front-end Development
Procurement
Project Management
Research
Social Media Marketing
Software Engineering
Tax
UX/UI Design
"""

def extract_job_details(text, apply_link):
    prompt = f"""
You are an AI assistant that extracts structured job information from unstructured text.
Given the following job description, extract the following fields:
- "title": The job title. Please add the employment start year to the end (if it can be found) - for example - 'Mechanical Engineering Placement 2026'
- "company": The company name.
- "location": The job location(s). Do NOT include regions, only cities, unless not city is specified.
- "salary_type": Classify the salary as one of: "Paid", "Unpaid", "Competitive". Use "Paid" if a specific amount is mentioned, "Unpaid" if the role is explicitly unpaid/voluntary, "Competitive" if described as competitive or not specified.
- "salary_amount": The numeric salary value or range only (e.g. "£25,000", "£14.50", "£20,000 - £25,000"). Set to null if unpaid or competitive.
- "salary_frequency": How the salary is paid. One of: "Hourly", "Daily", "Weekly", "Monthly", "Annual". Infer from context (e.g. "per hour" → "Hourly", "per annum" / "a year" / graduate salary → "Annual"). Set to null if unpaid or competitive.
- "salary_perks": Any perks, benefits, or additional compensation mentioned (e.g. pension, holiday allowance, gym membership). Extract as plain text. Set to null if none mentioned.
- "job_type": Specify if the job is one of these: "Internship (1 Month+)", "Placement (10 Months+)", "Graduate Job", "Graduate Scheme", "Level 2 Apprenticeship", "Level 3 Apprenticeship", "Higher Level Apprenticeship", "Degree Apprenticeship", "School Leaver Programme", "Work Experience", "Insight/Vacation Scheme (< 4 Weeks)", "Insight Day";
- "description": "Extract the complete job description from the source without omitting any details. Format the entire output in HTML (REMOVE ALL SPACES BETWEEN TAGS, i.e. <h2>text</h2><p>text</p>) using <h2> for main section headers, <h3> for sub-headings, and <ul><li> for lists. Ensure that every piece of the original content is captured. Do not include any of the page HTML elements or tags, just the content, no button, no label, no checkboxes, IDs, etc. Allowed tags: h2, h3, li, p, strong, b, em, i, u. lists MUST BE formatted like this in a single line and NO SPACES <li>1</li><li>2</li><li>3</li><li>4</li> NO INDENTATION! AND DO NOT USE <ul><ol></ul></ol>. Do not include page elements such as buttons, labels, checkboxes, cookies settings, IDs, etc. Just the content. Usually the job description will be inside a single container, therefore, for anything outside of it use logic to determine if part or not of the description. Any copy in the job description that talks about the company instead of the role should be placed at the bottom of the job description under a heading called <h2>About the Company</h2> before the 'apply' section (as sometimes this is all at the top). Any copy that's about applying should all be moved to be under the 'apply' section. anything about 'what we are looking for' / 'eligibility' is put in bulleted lists / anything about 'rewards' / 'benefits' / 'salary' is put in bulleted lists / anything about 'day-to-day' / 'the role' / 'what you will be doing' is put in bulleted lists.
- "apply_link": This exact URL: {apply_link}.
- "application_deadline": "Scan the job description for any of these keywords: 'Apply by', 'Closing date', 'Deadline', or 'Application Deadline'. If one is found, extract the date that immediately follows the keyword (e.g., from 'Apply by Jan 1, 2026', extract 'Jan 1, 2026'). If no valid date is present, set this field to 'null'."
- "relevant_year": Try and match the relevant year by using the job title, for example, Graduate, Placement. Select based on job description/title, if N/A just keep it as NULL: "Is job relevant to Graduates?" or "Is job relevant to 1st years?" or "Is job relevant to 2nd years?" or "Is job relevant to 3rd years?". Out put this as 1st year, 2nd year, 3rd year or Graduate, please note that some jobs you can have more than one, i.e. (3rd years, Graduates).
- "Employment Start Date": Find any dates refering to the start of employment (if available).

Job Description:
{text}

# EXTRA INFORMATION:
Instructions:
1. Extract "job_tags": Select THE MAXIMUM OF 2 tags from the following list.
2. For "application_deadline" and "Employment Start Date", convert dates to dd/mm/yyyy.
Tags List:
{TAGS_LIST}

Extracted Information in JSON:
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=16384,
            top_p=1
        )
        usage = response.get("usage", {})
        logger.info("Token usage: %s", usage)
        return json.loads(response['choices'][0]['message']['content'].strip())
    except Exception as e:
        logger.error(f"Error with OpenAI API: {e}")
        return None

import React, { useState, useRef } from 'react';
import './App.css';

const BULK_EDIT_FIELDS = [
  { key: 'title', label: 'Job Title' },
  { key: 'company', label: 'Company' },
  { key: 'location', label: 'Location' },
  { key: 'salary_type', label: 'Salary Type' },
  { key: 'salary_amount', label: 'Salary Amount' },
  { key: 'salary_frequency', label: 'Frequency' },
  { key: 'salary_perks', label: 'Perks & Benefits' },
  { key: 'job_type', label: 'Job Type' },
  { key: 'apply_link', label: 'Apply Link' },
  { key: 'application_deadline', label: 'Application Deadline' },
  { key: 'job_tags', label: 'Tags (comma-separated)' },
  { key: 'employment_start_date', label: 'Employment Start Date' },
  { key: 'relevant_year', label: 'Relevant Year' },
];

const API_BASE = process.env.REACT_APP_API_BASE_URL || '';
// Domain used inside generated job URLs. Defaults to wherever the app is open;
// set REACT_APP_PUBLIC_BASE_URL to force the deployed domain during local dev.
const PUBLIC_BASE = process.env.REACT_APP_PUBLIC_BASE_URL || '';

const ACCEPTED_EXTENSIONS = ['docx', 'pdf', 'txt', 'md'];

const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    const el = document.createElement('textarea');
    el.value = text;
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(el);
    return ok;
  }
};

/* ─── Shared job-list state (one instance per tab) ─────────────── */
const useJobList = () => {
  const [jobDataList, setJobDataList] = useState([]);
  const [selectedJobs, setSelectedJobs] = useState(new Set());
  const [bulkModal, setBulkModal] = useState({ open: false, field: '', value: '' });

  const appendJobs = (jobs) => setJobDataList(prev => [...prev, ...jobs]);

  const resetList = () => {
    setJobDataList([]);
    setSelectedJobs(new Set());
  };

  const updateJobField = (index, field, value) => {
    setJobDataList(prev => {
      const next = [...prev];
      next[index] = { ...next[index], job_details: { ...next[index].job_details, [field]: value } };
      return next;
    });
  };

  const updateJobMeta = (index, patch) => {
    setJobDataList(prev => {
      const next = [...prev];
      next[index] = { ...next[index], ...patch };
      return next;
    });
  };

  const deleteJob = (index) => {
    setJobDataList(prev => prev.filter((_, i) => i !== index));
    setSelectedJobs(prev => {
      const next = new Set();
      prev.forEach(i => { if (i < index) next.add(i); else if (i > index) next.add(i - 1); });
      return next;
    });
  };

  const toggleSelectJob = (index) => {
    setSelectedJobs(prev => {
      const next = new Set(prev);
      next.has(index) ? next.delete(index) : next.add(index);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedJobs(
      selectedJobs.size === jobDataList.length
        ? new Set()
        : new Set(jobDataList.map((_, i) => i))
    );
  };

  const applyBulkEdit = () => {
    const { field, value } = bulkModal;
    if (!field) return;
    const parsed = field === 'job_tags'
      ? value.split(',').map(t => t.trim()).filter(Boolean)
      : value;
    setJobDataList(prev =>
      prev.map((job, i) =>
        selectedJobs.has(i)
          ? { ...job, job_details: { ...job.job_details, [field]: parsed } }
          : job
      )
    );
    setBulkModal({ open: false, field: '', value: '' });
  };

  const allSelected = jobDataList.length > 0 && selectedJobs.size === jobDataList.length;

  return {
    jobDataList, setJobDataList, appendJobs, resetList,
    selectedJobs, toggleSelectJob, toggleSelectAll, allSelected,
    updateJobField, updateJobMeta, deleteJob,
    bulkModal, setBulkModal, applyBulkEdit,
  };
};

/* ─── App shell with tabs ──────────────────────────────────────── */
const App = () => {
  const [activeTab, setActiveTab] = useState('scraper');
  const scraperList = useJobList();
  const extractorList = useJobList();

  return (
    <div className="app-container">
      <header className="app-header">
        <h1 className="app-title">Higherin Jobs Listings Scraper</h1>
        <p className="app-subtitle">
          {activeTab === 'scraper'
            ? 'Paste one or more job URLs to extract and moderate listings'
            : 'Upload job description files (.docx, .pdf, .txt) to extract and moderate listings'}
        </p>
        <div className="tabs">
          <button
            className={activeTab === 'scraper' ? 'tab active' : 'tab'}
            onClick={() => setActiveTab('scraper')}
          >
            URL Scraper
          </button>
          <button
            className={activeTab === 'extractor' ? 'tab active' : 'tab'}
            onClick={() => setActiveTab('extractor')}
          >
            File Extractor
          </button>
        </div>
      </header>

      <div style={activeTab === 'scraper' ? undefined : { display: 'none' }}>
        <ScraperTab listApi={scraperList} />
      </div>
      <div style={activeTab === 'extractor' ? undefined : { display: 'none' }}>
        <ExtractorTab listApi={extractorList} />
      </div>
    </div>
  );
};

/* ─── Tab 1: URL scraper (existing behaviour) ──────────────────── */
const ScraperTab = ({ listApi }) => {
  const [urls, setUrls] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchProgress, setFetchProgress] = useState({ current: 0, total: 0 });

  const chunkArray = (array, chunkSize) => {
    const chunks = [];
    for (let i = 0; i < array.length; i += chunkSize) {
      chunks.push(array.slice(i, i + chunkSize));
    }
    return chunks;
  };

  const fetchJobDetails = async () => {
    setLoading(true);
    listApi.resetList();

    try {
      const urlArray = urls.split(',').map(url => url.trim()).filter(Boolean);
      const batchSize = 1;
      const batches = chunkArray(urlArray, batchSize);
      let aggregatedResults = [];
      const maxRetries = 3;

      setFetchProgress({ current: 0, total: batches.length });

      for (let batchIndex = 0; batchIndex < batches.length; batchIndex++) {
        let retries = 0;
        let batchProcessed = false;

        while (retries < maxRetries && !batchProcessed) {
          try {
            const response = await fetch(`${API_BASE}/api/scrape-multiple`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ urls: urlArray, batch: batchIndex, batch_size: batchSize }),
            });

            if (!response.ok) throw new Error(`Batch ${batchIndex} failed: ${response.status}`);

            const batchResults = await response.json();
            aggregatedResults = aggregatedResults.concat(batchResults);
            listApi.appendJobs(batchResults);
            setFetchProgress({ current: batchIndex + 1, total: batches.length });
            batchProcessed = true;
            await new Promise(r => setTimeout(r, 1000));

          } catch (error) {
            retries++;
            if (retries < maxRetries) {
              await new Promise(r => setTimeout(r, 2000));
            } else {
              alert(`Batch ${batchIndex} failed after ${retries} retries.`);
              batchProcessed = true;
            }
          }
        }
      }

      const failed = aggregatedResults.filter(j => j.error);
      if (failed.length > 0) alert('Failed: ' + failed.map(j => j.url).join(', '));

    } catch (error) {
      console.error(error);
      alert('Failed to fetch job details. Check the console for more details.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="input-container">
        <label htmlFor="urls" className="label">Job URLs (comma-separated)</label>
        <textarea
          id="urls"
          value={urls}
          onChange={e => setUrls(e.target.value)}
          placeholder="https://example.com/job/1, https://example.com/job/2"
          className="textarea"
          rows={3}
        />
        <button onClick={fetchJobDetails} disabled={loading} className={`button ${loading ? 'button-disabled' : ''}`}>
          {loading
            ? `Processing ${fetchProgress.current} / ${fetchProgress.total}…`
            : 'Fetch Job Details'}
        </button>
      </div>

      {loading && (
        <div className="loading-container">
          <div className="loading-track">
            <div
              className="loading-fill"
              style={{ width: fetchProgress.total ? `${(fetchProgress.current / fetchProgress.total) * 100}%` : '0%' }}
            />
          </div>
          <p className="loading-text">
            Scraping job {fetchProgress.current + 1} of {fetchProgress.total}…
          </p>
        </div>
      )}

      <JobListSection listApi={listApi} exportName="all_jobs.json" />
    </>
  );
};

/* ─── Tab 2: File extractor ────────────────────────────────────── */
const ExtractorTab = ({ listApi }) => {
  const [queuedFiles, setQueuedFiles] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState({ label: '', current: 0, total: 0 });
  const fileInputRef = useRef(null);

  const addFiles = (fileList) => {
    const incoming = Array.from(fileList).filter(file => {
      const ext = file.name.split('.').pop().toLowerCase();
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        alert(`"${file.name}" skipped — supported types: ${ACCEPTED_EXTENSIONS.map(e => '.' + e).join(', ')}`);
        return false;
      }
      if (file.size > 4 * 1024 * 1024) {
        alert(`"${file.name}" skipped — files must be under 4MB.`);
        return false;
      }
      return true;
    });
    setQueuedFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...incoming.filter(f => !names.has(f.name))];
    });
  };

  const removeFile = (name) => setQueuedFiles(prev => prev.filter(f => f.name !== name));

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  };

  const extractFromFiles = async () => {
    if (queuedFiles.length === 0) return;
    setProcessing(true);
    const errors = [];

    try {
      // Phase 1 — upload each file, get back its individual job chunks
      const allChunks = [];
      for (let i = 0; i < queuedFiles.length; i++) {
        const file = queuedFiles[i];
        setProgress({ label: `Reading ${file.name} (file ${i + 1} of ${queuedFiles.length})…`, current: i, total: queuedFiles.length });
        try {
          const formData = new FormData();
          formData.append('file', file);
          const response = await fetch(`${API_BASE}/api/extract-file`, { method: 'POST', body: formData });
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.error || `Failed with status ${response.status}`);
          payload.jobs.forEach(chunk => allChunks.push({ ...chunk, source: payload.filename }));
        } catch (error) {
          console.error(error);
          errors.push(`${file.name}: ${error.message}`);
        }
      }

      // Phase 2 — run the structured extraction per job chunk (mirrors the URL batch pattern)
      const maxRetries = 3;
      setProgress({ label: '', current: 0, total: allChunks.length });

      for (let i = 0; i < allChunks.length; i++) {
        const chunk = allChunks[i];
        const chunkLabel = chunk.title || `job ${i + 1}`;
        setProgress({
          label: `Extracting "${chunkLabel}" (${i + 1} of ${allChunks.length})…`,
          current: i,
          total: allChunks.length,
        });

        let retries = 0;
        let done = false;
        while (retries < maxRetries && !done) {
          try {
            const response = await fetch(`${API_BASE}/api/extract-file-job`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ text: chunk.text, source: chunk.source }),
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || `Failed with status ${response.status}`);
            listApi.appendJobs([{ source: chunk.source, job_details: payload.job_details }]);
            done = true;
          } catch (error) {
            retries++;
            if (retries < maxRetries) {
              await new Promise(r => setTimeout(r, 2000));
            } else {
              errors.push(`${chunk.source} — ${chunkLabel}: ${error.message}`);
              done = true;
            }
          }
        }
        setProgress(prev => ({ ...prev, current: i + 1 }));
      }

      if (errors.length > 0) alert('Some items failed:\n' + errors.join('\n'));
      setQueuedFiles([]);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <>
      <div className="input-container">
        <label className="label">Job Description Files (.docx, .pdf, .txt, .md)</label>
        <div
          className={`dropzone ${dragOver ? 'dragover' : ''}`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <p className="dropzone-title">Drag &amp; drop files here, or click to browse</p>
          <p className="dropzone-hint">One file can contain several job postings — each is extracted as its own card</p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS.map(e => '.' + e).join(',')}
            style={{ display: 'none' }}
            onChange={e => { addFiles(e.target.files); e.target.value = ''; }}
          />
        </div>

        {queuedFiles.length > 0 && (
          <div className="file-chips">
            {queuedFiles.map(file => (
              <span key={file.name} className="file-chip">
                {file.name}
                <button className="file-chip-remove" onClick={() => removeFile(file.name)} disabled={processing}>✕</button>
              </span>
            ))}
          </div>
        )}

        <button
          onClick={extractFromFiles}
          disabled={processing || queuedFiles.length === 0}
          className={`button ${processing || queuedFiles.length === 0 ? 'button-disabled' : ''}`}
        >
          {processing
            ? 'Extracting…'
            : `Extract Jobs${queuedFiles.length > 0 ? ` from ${queuedFiles.length} file${queuedFiles.length !== 1 ? 's' : ''}` : ''}`}
        </button>
      </div>

      {processing && (
        <div className="loading-container">
          <div className="loading-track">
            <div
              className="loading-fill"
              style={{ width: progress.total ? `${(progress.current / progress.total) * 100}%` : '0%' }}
            />
          </div>
          <p className="loading-text">{progress.label || 'Working…'}</p>
        </div>
      )}

      <JobListSection listApi={listApi} exportName="extracted_jobs.json" />
    </>
  );
};

/* ─── Shared list section: bulk bar, cards, modals, URL output ─── */
const JobListSection = ({ listApi, exportName }) => {
  const {
    jobDataList, selectedJobs, toggleSelectJob, toggleSelectAll, allSelected,
    updateJobField, updateJobMeta, deleteJob,
    bulkModal, setBulkModal, applyBulkEdit,
  } = listApi;

  const [urlsModal, setUrlsModal] = useState({ open: false, rows: [], copiedAll: false });
  const [generatingUrls, setGeneratingUrls] = useState(false);

  const publicBaseUrl = PUBLIC_BASE || window.location.origin;

  const requestUrls = async (jobs) => {
    const response = await fetch(`${API_BASE}/api/encode-job-urls`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jobs: jobs.map(j => j.job_details || {}), base_url: publicBaseUrl }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Failed with status ${response.status}`);
    return payload.urls;
  };

  const generateUrlForCard = async (index) => {
    updateJobMeta(index, { generating_url: true });
    try {
      const [result] = await requestUrls([jobDataList[index]]);
      if (result.error) throw new Error(result.error);
      updateJobMeta(index, {
        generated_url: result.url,
        generated_url_too_long: result.too_long,
        generating_url: false,
      });
    } catch (error) {
      console.error(error);
      alert(`Failed to generate URL: ${error.message}`);
      updateJobMeta(index, { generating_url: false });
    }
  };

  const generateUrlsBulk = async () => {
    const indices = selectedJobs.size > 0
      ? [...selectedJobs].sort((a, b) => a - b)
      : jobDataList.map((_, i) => i);
    if (indices.length === 0) return;

    setGeneratingUrls(true);
    try {
      const results = await requestUrls(indices.map(i => jobDataList[i]));
      const rows = results.map((r, k) => ({ ...r, index: indices[k], copied: false }));
      rows.forEach(row => {
        if (row.url) {
          updateJobMeta(row.index, { generated_url: row.url, generated_url_too_long: row.too_long });
        }
      });
      setUrlsModal({ open: true, rows, copiedAll: false });
    } catch (error) {
      console.error(error);
      alert(`Failed to generate URLs: ${error.message}`);
    } finally {
      setGeneratingUrls(false);
    }
  };

  const copyAllUrls = async () => {
    const joined = urlsModal.rows.filter(r => r.url).map(r => r.url).join(', ');
    if (await copyToClipboard(joined)) {
      setUrlsModal(prev => ({ ...prev, copiedAll: true }));
      setTimeout(() => setUrlsModal(prev => ({ ...prev, copiedAll: false })), 1600);
    }
  };

  const copyRowUrl = async (rowIndex) => {
    const row = urlsModal.rows[rowIndex];
    if (row?.url && await copyToClipboard(row.url)) {
      setUrlsModal(prev => ({
        ...prev,
        rows: prev.rows.map((r, i) => i === rowIndex ? { ...r, copied: true } : r),
      }));
      setTimeout(() => setUrlsModal(prev => ({
        ...prev,
        rows: prev.rows.map((r, i) => i === rowIndex ? { ...r, copied: false } : r),
      })), 1600);
    }
  };

  const exportAllToJson = () => {
    const blob = new Blob([JSON.stringify(jobDataList, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = exportName; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      {jobDataList.length > 0 && (
        <div className="bulk-bar-sticky-wrap">
          <div className="bulk-bar">
            <label className="select-all-label">
              <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} />
              {allSelected ? 'Deselect All' : 'Select All'}
            </label>
            {selectedJobs.size > 0 && (
              <button className="bulk-edit-button" onClick={() => setBulkModal({ open: true, field: '', value: '' })}>
                Bulk Edit · {selectedJobs.size} selected
              </button>
            )}
            <span className="bulk-bar-count">{jobDataList.length} job{jobDataList.length !== 1 ? 's' : ''}</span>
            <button
              onClick={generateUrlsBulk}
              disabled={generatingUrls}
              className="action-button generate-urls-button"
            >
              {generatingUrls
                ? 'Generating…'
                : `Generate URLs${selectedJobs.size > 0 ? ` (${selectedJobs.size})` : ' (all)'}`}
            </button>
            <button onClick={exportAllToJson} className="action-button export-all-button">
              Export All
            </button>
          </div>
        </div>
      )}

      <div className="job-list">
        {jobDataList.map((jobData, index) => (
          <JobCard
            key={index}
            jobData={jobData}
            selected={selectedJobs.has(index)}
            onToggleSelect={() => toggleSelectJob(index)}
            onFieldUpdate={(field, value) => updateJobField(index, field, value)}
            onDelete={() => deleteJob(index)}
            onGenerateUrl={() => generateUrlForCard(index)}
          />
        ))}
      </div>

      {bulkModal.open && (
        <div className="modal-overlay" onClick={() => setBulkModal({ open: false, field: '', value: '' })}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">
              Bulk Edit
              <span className="modal-title-count">{selectedJobs.size} job{selectedJobs.size !== 1 ? 's' : ''}</span>
            </h3>
            <div className="modal-body">
              <label className="modal-label">Field to edit</label>
              <select
                className="modal-select"
                value={bulkModal.field}
                onChange={e => setBulkModal(prev => ({ ...prev, field: e.target.value, value: '' }))}
              >
                <option value="">— Select a field —</option>
                {BULK_EDIT_FIELDS.map(({ key, label }) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
              {bulkModal.field && (
                <>
                  <label className="modal-label">New value</label>
                  <input
                    type="text"
                    className="modal-input"
                    value={bulkModal.value}
                    onChange={e => setBulkModal(prev => ({ ...prev, value: e.target.value }))}
                    placeholder={bulkModal.field === 'job_tags' ? 'e.g. Sales, Marketing' : ''}
                    autoFocus
                  />
                </>
              )}
            </div>
            <div className="modal-footer">
              <button className="modal-cancel" onClick={() => setBulkModal({ open: false, field: '', value: '' })}>Cancel</button>
              <button className="modal-apply" onClick={applyBulkEdit} disabled={!bulkModal.field}>Apply</button>
            </div>
          </div>
        </div>
      )}

      {urlsModal.open && (
        <div className="modal-overlay" onClick={() => setUrlsModal({ open: false, rows: [], copiedAll: false })}>
          <div className="modal urls-modal" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">
              Generated URLs
              <span className="modal-title-count">{urlsModal.rows.length} URL{urlsModal.rows.length !== 1 ? 's' : ''}</span>
            </h3>
            <div className="modal-body">
              <p className="urls-modal-hint">
                Paste these into the scraper as comma-separated URLs. They only resolve where this app is deployed
                ({publicBaseUrl.replace(/^https?:\/\//, '')}).
              </p>
              <div className="urls-modal-list">
                {urlsModal.rows.map((row, i) => (
                  <div key={i} className="url-row">
                    <div className="url-row-main">
                      <span className="url-row-title">{row.title || `Job ${row.index + 1}`}</span>
                      {row.error
                        ? <span className="url-row-error">{row.error}</span>
                        : <span className="url-row-url">{row.url}</span>}
                      {row.too_long && <span className="url-row-warning">Long URL ({row.length} chars) — trim the description if the target scraper rejects it</span>}
                    </div>
                    {row.url && (
                      <button className="action-button" onClick={() => copyRowUrl(i)}>
                        {row.copied ? 'Copied!' : 'Copy'}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <div className="modal-footer">
              <button className="modal-cancel" onClick={() => setUrlsModal({ open: false, rows: [], copiedAll: false })}>Close</button>
              <button className="modal-apply" onClick={copyAllUrls}>
                {urlsModal.copiedAll ? 'Copied!' : 'Copy All (comma-separated)'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

/* ─── Job card (shared by both tabs) ───────────────────────────── */
const JobCard = ({ jobData, selected, onToggleSelect, onFieldUpdate, onDelete, onGenerateUrl }) => {
  const [expanded, setExpanded] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);

  const jd = jobData.job_details || {};
  const sourceLabel = jobData.url || jobData.source;

  const missing = (field) =>
    !jd[field] || jd[field] === '' || jd[field] === 'null';

  const isIncomplete = [
    'title', 'company', 'location', 'salary_type', 'salary_amount',
    'salary_frequency', 'job_type', 'apply_link', 'application_deadline',
    'description', 'job_tags', 'employment_start_date', 'relevant_year',
  ].some(missing);

  const cardClass = ['job-card', isIncomplete ? 'incomplete' : '', selected ? 'selected' : ''].filter(Boolean).join(' ');

  const exportToJson = () => {
    const blob = new Blob([JSON.stringify(jobData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${jd.title || 'job'}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  const copyGeneratedUrl = async () => {
    if (jobData.generated_url && await copyToClipboard(jobData.generated_url)) {
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 1600);
    }
  };

  // Fetch + blob instead of a plain link: in local dev, navigating to the URL
  // hits the CRA dev server (which doesn't proxy text/html navigations), so a
  // normal link would show the React app instead of the rendered job page.
  const previewGeneratedUrl = async () => {
    // Open the window synchronously (inside the click gesture) so the browser
    // doesn't popup-block it, then load the fetched page into it.
    const win = window.open('', '_blank');
    try {
      const response = await fetch(jobData.generated_url);
      if (!response.ok) throw new Error(`Status ${response.status}`);
      const html = await response.text();
      if (!win) throw new Error('Popup blocked by the browser');
      const blobUrl = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
      win.location.href = blobUrl;
      setTimeout(() => URL.revokeObjectURL(blobUrl), 30000);
    } catch (error) {
      if (win) win.close();
      console.error(error);
      alert(`Could not preview the job page: ${error.message}`);
    }
  };

  const f = (field) => ({
    value: field === 'job_tags'
      ? (Array.isArray(jd[field]) ? jd[field].join(', ') : jd[field] || '')
      : (jd[field] || ''),
    onChange: (e) => onFieldUpdate(
      field,
      field === 'job_tags'
        ? e.target.value.split(',').map(t => t.trim())
        : e.target.value
    ),
    className: missing(field) ? 'input-field missing' : 'input-field',
  });

  return (
    <div className={cardClass}>
      {/* ── Header ── */}
      <div className="card-header">
        <label className="card-select-label">
          <input type="checkbox" checked={selected} onChange={onToggleSelect} />
          Select
        </label>
        {sourceLabel && (
          <div className="card-source" title={sourceLabel}>
            {jobData.url ? '🔗' : '📄'} {sourceLabel}
          </div>
        )}
        <div className="card-header-body">
          <div className="field-group">
            <label className="field-label">Job Title</label>
            <input type="text" placeholder="Job Title" {...f('title')} className={missing('title') ? 'card-title-input missing' : 'card-title-input'} />
          </div>
          <div className="field-group">
            <label className="field-label">Job Type</label>
            <input type="text" placeholder="Job Type" {...f('job_type')} className={missing('job_type') ? 'card-title-input missing' : 'card-title-input'} />
          </div>
          <div className="field-group">
            <label className="field-label">Company</label>
            <input type="text" placeholder="Company" {...f('company')} className={missing('company') ? 'card-subtitle-input missing' : 'card-subtitle-input'} />
          </div>
          <div className="field-group">
            <label className="field-label">Location</label>
            <input type="text" placeholder="Location" {...f('location')} className={missing('location') ? 'card-subtitle-input missing' : 'card-subtitle-input'} />
          </div>
        </div>
      </div>

      {/* ── Main fields ── */}
      <div className="card-fields-grid">
        <div className="field-group field-group--full">
          <label className="field-label">Apply Link</label>
          <input type="text" placeholder="https://…" {...f('apply_link')} />
        </div>

        {/* Salary block */}
        <div className="salary-group">
          <p className="salary-group-header">Salary</p>
          <div className="salary-group-fields">
            <div className="field-group">
              <label className="field-label">Type</label>
              <input type="text" placeholder="Paid / Unpaid / Competitive" {...f('salary_type')} />
            </div>
            <div className="field-group">
              <label className="field-label">Amount</label>
              <input type="text" placeholder="£25,000" {...f('salary_amount')} />
            </div>
            <div className="field-group">
              <label className="field-label">Frequency</label>
              <input type="text" placeholder="Annual / Hourly…" {...f('salary_frequency')} />
            </div>
            <div className="field-group field-group--full">
              <label className="field-label">Perks &amp; Benefits</label>
              <input type="text" placeholder="Pension, holidays…" {...f('salary_perks')} className="input-field" />
            </div>
          </div>
        </div>

        {/* Description */}
        <div className="field-group field-group--full">
          <label className="field-label">Description</label>
          <textarea placeholder="Job description…" {...f('description')} className={missing('description') ? 'textarea description-textarea missing' : 'textarea description-textarea'} />
          <button onClick={() => setShowPreview(v => !v)} className="preview-toggle-link">
            {showPreview ? '▲ Hide preview' : '▼ Show preview'}
          </button>
          {showPreview && (
            <div className="description-preview" dangerouslySetInnerHTML={{ __html: jd.description || '' }} />
          )}
        </div>
      </div>

      {/* ── Expanded section ── */}
      {expanded && (
        <div className="job-extra">
          <div className="card-fields-grid">
            <div className="field-group">
              <label className="field-label">Tags</label>
              <input type="text" placeholder="Sales, Marketing…" {...f('job_tags')} />
            </div>
            <div className="field-group">
              <label className="field-label">Application Deadline</label>
              <input type="text" placeholder="dd/mm/yyyy" {...f('application_deadline')} />
            </div>
            <div className="field-group">
              <label className="field-label">Employment Start Date</label>
              <input type="text" placeholder="dd/mm/yyyy" {...f('employment_start_date')} />
            </div>
            <div className="field-group">
              <label className="field-label">Relevant Year</label>
              <input type="text" placeholder="Graduate, 3rd year…" {...f('relevant_year')} />
            </div>
          </div>
        </div>
      )}

      {/* ── Generated URL ── */}
      {jobData.generated_url && (
        <div className="url-result">
          <span className="url-result-text" title={jobData.generated_url}>{jobData.generated_url}</span>
          <button className="action-button" onClick={copyGeneratedUrl}>{copiedUrl ? 'Copied!' : 'Copy'}</button>
          <button className="action-button" onClick={previewGeneratedUrl}>Preview</button>
          {jobData.generated_url_too_long && (
            <span className="url-row-warning">Long URL — trim the description if the target scraper rejects it</span>
          )}
        </div>
      )}

      {/* ── Actions ── */}
      <div className="job-card-actions">
        <button onClick={() => setExpanded(v => !v)} className="action-button">
          {expanded ? 'Collapse' : 'Show More'}
        </button>
        <button onClick={exportToJson} className="action-button">Export JSON</button>
        <button onClick={onGenerateUrl} disabled={jobData.generating_url} className="action-button">
          {jobData.generating_url ? 'Generating…' : (jobData.generated_url ? 'Regenerate URL' : 'Generate URL')}
        </button>
        <button onClick={onDelete} className="action-button delete-button">Delete</button>
      </div>
    </div>
  );
};

export default App;

import React, { useState } from 'react';
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

const App = () => {
  const [urls, setUrls] = useState('');
  const [jobDataList, setJobDataList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchProgress, setFetchProgress] = useState({ current: 0, total: 0 });
  const [selectedJobs, setSelectedJobs] = useState(new Set());
  const [bulkModal, setBulkModal] = useState({ open: false, field: '', value: '' });

  const chunkArray = (array, chunkSize) => {
    const chunks = [];
    for (let i = 0; i < array.length; i += chunkSize) {
      chunks.push(array.slice(i, i + chunkSize));
    }
    return chunks;
  };

  const fetchJobDetails = async () => {
    setLoading(true);
    setJobDataList([]);
    setSelectedJobs(new Set());
    const baseUrl = process.env.REACT_APP_API_BASE_URL || '';

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
            const response = await fetch(`${baseUrl}/api/scrape-multiple`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ urls: urlArray, batch: batchIndex, batch_size: batchSize }),
            });

            if (!response.ok) throw new Error(`Batch ${batchIndex} failed: ${response.status}`);

            const batchResults = await response.json();
            aggregatedResults = aggregatedResults.concat(batchResults);
            setJobDataList(prev => [...prev, ...batchResults]);
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

  const updateJobField = (index, field, value) => {
    setJobDataList(prev => {
      const next = [...prev];
      next[index] = { ...next[index], job_details: { ...next[index].job_details, [field]: value } };
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

  const exportAllToJson = () => {
    const blob = new Blob([JSON.stringify(jobDataList, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'all_jobs.json'; a.click();
    URL.revokeObjectURL(url);
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

  return (
    <div className="app-container">
      <header className="app-header">
        <h1 className="app-title">Higherin Jobs Listings Scraper</h1>
        <p className="app-subtitle">Paste one or more job URLs to extract and moderate listings</p>
      </header>

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
    </div>
  );
};

const JobCard = ({ jobData, selected, onToggleSelect, onFieldUpdate, onDelete }) => {
  const [expanded, setExpanded] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const jd = jobData.job_details || {};

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

      {/* ── Actions ── */}
      <div className="job-card-actions">
        <button onClick={() => setExpanded(v => !v)} className="action-button">
          {expanded ? 'Collapse' : 'Show More'}
        </button>
        <button onClick={exportToJson} className="action-button">Export JSON</button>
        <button onClick={onDelete} className="action-button delete-button">Delete</button>
      </div>
    </div>
  );
};

export default App;

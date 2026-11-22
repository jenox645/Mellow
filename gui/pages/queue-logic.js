// The Queue's logic: its state, effects, API calls and handlers, shared by every theme.
// useQueuePage(props) takes what the App hands the Queue and returns everything a view
// draws and every handler it calls (the view itself never calls the API).
'use strict';

import { API, cancelShownDownload } from '../lib/api.js';
import { QUEUE_POLL_MS } from '../lib/constants.js';

export function useQueuePage(props) {
  const { dlState, showNotif, activeJobs, playlistItems, failedItems, syncPlan } = props;
  const isDownloading = dlState && dlState.pct !== undefined;
  // Every running job (Concurrent Downloads > 1), not just the one on the Feed
  const activeCount = Math.max(Object.keys(activeJobs || {}).length, isDownloading ? 1 : 0);
  const queueCount = playlistItems ? playlistItems.length : 0;
  const [qTab, setQTab] = React.useState('pending');
  // The IN FOLDER tab leaves with the sync it belongs to
  React.useEffect(() => { if (!syncPlan && qTab === 'have') setQTab('pending'); }, [syncPlan, qTab]);
  const [jobs, setJobs] = React.useState([]);

  const loadJobs = React.useCallback(() => {
    API.get('/api/queue/status').then(d => setJobs(d.jobs || [])).catch(() => {});
  }, []);

  // The backend job queue (queued vault syncs, second URLs) — distinct from
  // the playlist items of the active job shown below
  React.useEffect(() => {
    loadJobs();
    const iv = setInterval(loadJobs, QUEUE_POLL_MS);
    return () => clearInterval(iv);
  }, [loadJobs]);

  const handleCancel = () => {
    cancelShownDownload(dlState).catch(e => showNotif('Error', e.message, 'error'));
  };

  const handleCancelJob = (job) => {
    API.del('/api/queue/' + job.id)
      .then(() => {
        showNotif(job.status === 'active' ? 'Cancelling' : 'Removed', job.label || job.url);
        setJobs(js => js.map(j => j.id === job.id ? { ...j, status: 'cancelled' } : j));
      })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  // ⏾ job: ▶ START NOW (clears its not_before)
  const startJobNow = (job) => {
    API.post('/api/queue/' + encodeURIComponent(job.id) + '/start-now', {})
      .then(loadJobs).catch(e => showNotif('Error', e.message, 'error'));
  };

  // A failed or cancelled job: ↻ RETRY runs it again, with the same options
  const retryJob = (job) => {
    API.post('/api/queue/' + encodeURIComponent(job.id) + '/retry', {})
      .then(() => { showNotif('Re-queued', job.label || job.url); loadJobs(); })
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  // Same options and folder as the job it failed in (a plain /api/download
  // used the Feed defaults: an MP3 playlist's item came back as video)
  const retryItem = (item) => (item.jobId
    ? API.post('/api/queue/' + encodeURIComponent(item.jobId) + '/retry', { url: item.url })
      .catch(e => { if (e.status === 404) return API.post('/api/download', { url: item.url }); throw e; })
    : API.post('/api/download', { url: item.url }));

  const handleRetryFailed = (item) => {
    if (!item.url) return;
    retryItem(item)
      .then(() => showNotif('Re-queued', item.url))
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const handleRetryAll = () => {
    const items = (failedItems || []).filter(i => i.url);
    const seen = new Set();
    const unique = items.filter(i => !seen.has(i.url) && seen.add(i.url));
    Promise.all(unique.map(i => retryItem(i).then(() => true, () => false)))
      .then(results => {
        const ok = results.filter(Boolean).length;
        showNotif('Re-queued', ok + ' of ' + unique.length + ' failed item(s)', ok === unique.length ? 'success' : 'warn');
      });
  };

  const handleReorder = (job, delta) => {
    const target = (job.queue_position || 0) + delta;
    if (target < 0) return;
    API.post('/api/queue/' + job.id + '/reorder', { index: target })
      .then(loadJobs)
      .catch(e => showNotif('Error', e.message, 'error'));
  };

  const queuedJobsCount = jobs.filter(j => j.status === 'queued').length;

  return {
    ...props,
    // the counters
    isDownloading, activeCount, queueCount, queuedJobsCount,
    // the server's job queue
    jobs, loadJobs, handleCancelJob, startJobNow, retryJob, handleReorder,
    // the shown download
    handleCancel,
    // the playlist panel's tabs, failed items
    qTab, setQTab, handleRetryFailed, handleRetryAll,
  };
}

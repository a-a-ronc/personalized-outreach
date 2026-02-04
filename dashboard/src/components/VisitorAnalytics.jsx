import { useState, useEffect } from "react";

function VisitorAnalytics({ fetchApi }) {
  const [analytics, setAnalytics] = useState(null);
  const [leadfeederStatus, setLeadfeederStatus] = useState(null);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [screenshots, setScreenshots] = useState([]);
  const [showScreenshots, setShowScreenshots] = useState(false);

  useEffect(() => {
    loadAllData();
  }, []);

  const loadAllData = async () => {
    setLoading(true);
    setError("");

    try {
      const [analyticsData, lfStatus, schedStatus] = await Promise.all([
        fetchApi("/api/visitors/analytics"),
        fetchApi("/api/integrations/leadfeeder/status").catch(() => null),
        fetchApi("/api/scheduler/status").catch(() => null)
      ]);

      setAnalytics(analyticsData);
      setLeadfeederStatus(lfStatus);
      setSchedulerStatus(schedStatus);

      // Load screenshots if Leadfeeder is configured
      if (lfStatus?.configured) {
        loadScreenshots();
      }
    } catch (err) {
      setError(err.message || "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  };

  const handleManualSync = async () => {
    setSyncing(true);
    try {
      const result = await fetchApi("/api/integrations/leadfeeder/sync", {
        method: "POST"
      });
      if (result.success) {
        alert(`Sync complete! Scraped ${result.companies_scraped} companies.`);
        loadAllData();
        loadScreenshots(); // Load screenshots after sync
      } else {
        alert(`Sync failed: ${result.error}`);
        loadScreenshots(); // Load screenshots even on failure to see what happened
      }
    } catch (err) {
      alert(`Sync error: ${err.message}`);
      loadScreenshots(); // Load screenshots even on error
    } finally {
      setSyncing(false);
    }
  };

  const loadScreenshots = async () => {
    try {
      const data = await fetchApi("/api/integrations/leadfeeder/screenshots");
      setScreenshots(data.screenshots || []);
    } catch (err) {
      console.error("Failed to load screenshots:", err);
    }
  };

  const formatPercent = (value) => {
    if (value === undefined || value === null) return "0%";
    return `${Math.round(value)}%`;
  };

  if (loading) {
    return <div className="loading-state">Loading analytics...</div>;
  }

  if (error) {
    return <div className="error-state">{error}</div>;
  }

  const tracking = analytics?.tracking || {};
  const reconciliation = analytics?.reconciliation || {};

  return (
    <div className="visitor-analytics">
      <div className="analytics-header">
        <h2>Visitor Analytics</h2>
        <p className="muted">Track and analyze website visitors</p>
      </div>

      {/* Summary Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{tracking.total_visits || 0}</div>
          <div className="stat-label">Total Visits</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{tracking.unique_ips || 0}</div>
          <div className="stat-label">Unique IPs</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{reconciliation.total_companies || 0}</div>
          <div className="stat-label">Identified Companies</div>
        </div>
        <div className="stat-card highlight">
          <div className="stat-value">{formatPercent(tracking.identification_rate)}</div>
          <div className="stat-label">Identification Rate</div>
        </div>
      </div>

      {/* Time-based Stats */}
      <div className="stats-section">
        <h3>Recent Activity</h3>
        <div className="stats-row">
          <div className="stat-item">
            <span className="stat-number">{tracking.visits_today || 0}</span>
            <span className="stat-desc">Visits Today</span>
          </div>
          <div className="stat-item">
            <span className="stat-number">{tracking.visits_this_week || 0}</span>
            <span className="stat-desc">Visits This Week</span>
          </div>
          <div className="stat-item">
            <span className="stat-number">{tracking.resolved_ips || 0}</span>
            <span className="stat-desc">IPs Resolved</span>
          </div>
          <div className="stat-item">
            <span className="stat-number">{reconciliation.enriched_count || 0}</span>
            <span className="stat-desc">Companies Enriched</span>
          </div>
        </div>
      </div>

      {/* Source Breakdown */}
      <div className="stats-section">
        <h3>Data Sources</h3>
        <div className="source-breakdown">
          {reconciliation.by_source && Object.entries(reconciliation.by_source).map(([source, count]) => (
            <div key={source} className="source-item">
              <span className={`source-badge source-${source}`}>{source}</span>
              <span className="source-count">{count} companies</span>
              <div className="source-bar">
                <div
                  className="source-fill"
                  style={{
                    width: `${(count / reconciliation.total_companies * 100) || 0}%`
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Top Industries */}
      {reconciliation.top_industries && reconciliation.top_industries.length > 0 && (
        <div className="stats-section">
          <h3>Top Industries</h3>
          <div className="industries-list">
            {reconciliation.top_industries.map((item, idx) => (
              <div key={idx} className="industry-item">
                <span className="industry-name">{item.industry || "Unknown"}</span>
                <span className="industry-count">{item.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Confidence Score */}
      <div className="stats-section">
        <h3>Data Quality</h3>
        <div className="quality-indicator">
          <div className="quality-label">Average Confidence Score</div>
          <div className="quality-bar">
            <div
              className="quality-fill"
              style={{ width: `${(reconciliation.average_confidence || 0) * 100}%` }}
            />
          </div>
          <div className="quality-value">
            {Math.round((reconciliation.average_confidence || 0) * 100)}%
          </div>
        </div>
      </div>

      {/* Integrations Status */}
      <div className="integrations-section">
        <h3>Integrations</h3>

        {/* Leadfeeder Status */}
        <div className="integration-card">
          <div className="integration-header">
            <div className="integration-name">
              <span className="integration-icon">🔍</span>
              Leadfeeder
            </div>
            <span className={`status-badge ${leadfeederStatus?.configured ? "status-replied" : "status-bounced"}`}>
              {leadfeederStatus?.configured ? "Configured" : "Not Configured"}
            </span>
          </div>

          {leadfeederStatus?.configured && (
            <div className="integration-details">
              <div className="detail-row">
                <span>Active Companies</span>
                <span>{leadfeederStatus?.active_companies || 0}</span>
              </div>
              <div className="detail-row">
                <span>Expiring Soon</span>
                <span>{leadfeederStatus?.expiring_soon || 0}</span>
              </div>
              {leadfeederStatus?.status?.last_sync_at && (
                <div className="detail-row">
                  <span>Last Sync</span>
                  <span>{new Date(leadfeederStatus.status.last_sync_at).toLocaleString()}</span>
                </div>
              )}
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button
                  className="primary-button"
                  onClick={handleManualSync}
                  disabled={syncing}
                >
                  {syncing ? "Syncing..." : "Sync Now"}
                </button>
                <button
                  className="secondary-button"
                  onClick={() => window.open('/vnc-viewer', 'VNC Viewer', 'width=1920,height=1080')}
                  title="Watch the browser in real-time"
                >
                  🎥 Watch Live
                </button>
                {screenshots.length > 0 && (
                  <button
                    className="secondary-button"
                    onClick={() => setShowScreenshots(true)}
                  >
                    📸 View Screenshots ({screenshots.length})
                  </button>
                )}
              </div>
            </div>
          )}

          {!leadfeederStatus?.configured && (
            <div className="integration-setup">
              <p className="muted">
                Set LEADFEEDER_EMAIL and LEADFEEDER_PASSWORD in your .env file to enable Leadfeeder integration.
              </p>
            </div>
          )}
        </div>

        {/* MaxMind Status */}
        <div className="integration-card">
          <div className="integration-header">
            <div className="integration-name">
              <span className="integration-icon">🌍</span>
              MaxMind GeoLite2
            </div>
            <span className={`status-badge ${tracking.resolved_ips > 0 ? "status-replied" : "status-sent"}`}>
              {tracking.resolved_ips > 0 ? "Active" : "Pending"}
            </span>
          </div>
          <div className="integration-details">
            <div className="detail-row">
              <span>IPs Resolved</span>
              <span>{tracking.resolved_ips || 0}</span>
            </div>
            <p className="muted" style={{ marginTop: "0.5rem" }}>
              IP-to-company resolution using MaxMind GeoLite2 database.
            </p>
          </div>
        </div>
      </div>

      {/* Scheduler Status */}
      {schedulerStatus && (
        <div className="scheduler-section">
          <h3>Background Jobs</h3>
          <div className="scheduler-status">
            <span className={`status-badge ${schedulerStatus.running ? "status-replied" : "status-bounced"}`}>
              {schedulerStatus.running ? "Running" : "Stopped"}
            </span>
          </div>

          {schedulerStatus.jobs && schedulerStatus.jobs.length > 0 && (
            <div className="jobs-list">
              {schedulerStatus.jobs.map((job, idx) => (
                <div key={idx} className="job-item">
                  <span className="job-name">{job.name}</span>
                  <span className="job-next">
                    Next: {job.next_run ? new Date(job.next_run).toLocaleString() : "—"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tracking Code */}
      <div className="tracking-code-section">
        <h3>Tracking Code</h3>
        <p className="muted">Add this code to your website to track visitors:</p>
        <div className="code-block">
          <pre>{`<script>
(function(w,d,s,u,k){
  w._vt=w._vt||[];
  var js,fjs=d.getElementsByTagName(s)[0];
  if(d.getElementById(k))return;
  js=d.createElement(s);js.id=k;
  js.src=u+'/api/track/script.js';
  fjs.parentNode.insertBefore(js,fjs);
})(window,document,'script','${window.location.origin.replace(':5173', ':7000')}','vt-script');
</script>`}</pre>
          <button
            className="copy-btn"
            onClick={() => {
              navigator.clipboard.writeText(`<script>
(function(w,d,s,u,k){
  w._vt=w._vt||[];
  var js,fjs=d.getElementsByTagName(s)[0];
  if(d.getElementById(k))return;
  js=d.createElement(s);js.id=k;
  js.src=u+'/api/track/script.js';
  fjs.parentNode.insertBefore(js,fjs);
})(window,document,'script','${window.location.origin.replace(':5173', ':7000')}','vt-script');
</script>`);
              alert("Copied to clipboard!");
            }}
          >
            Copy
          </button>
        </div>
      </div>

      {/* Screenshot Viewer Modal */}
      {showScreenshots && (
        <div className="modal-overlay" onClick={() => setShowScreenshots(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: "900px", maxHeight: "90vh", overflow: "auto" }}>
            <div className="modal-header">
              <h3>Leadfeeder Scrape Screenshots</h3>
              <button className="close-button" onClick={() => setShowScreenshots(false)}>×</button>
            </div>
            <div className="modal-body">
              {screenshots.length === 0 ? (
                <p className="muted">No screenshots available. Run a sync to generate screenshots.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                  {screenshots.map((screenshot, idx) => (
                    <div key={idx} style={{ border: "1px solid #ddd", borderRadius: "8px", padding: "1rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                        <strong>{screenshot.filename}</strong>
                        <span className="muted">
                          {new Date(screenshot.timestamp * 1000).toLocaleString()}
                        </span>
                      </div>
                      <img
                        src={screenshot.url}
                        alt={screenshot.filename}
                        style={{ width: "100%", border: "1px solid #eee", borderRadius: "4px" }}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default VisitorAnalytics;

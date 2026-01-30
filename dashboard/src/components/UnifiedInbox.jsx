import { useState, useEffect } from "react";

const CHANNEL_FILTERS = [
  { id: "all", label: "All Activity", icon: "📥" },
  { id: "email", label: "Emails", icon: "📧" },
  { id: "call", label: "Calls", icon: "📞" },
  { id: "linkedin", label: "LinkedIn", icon: "💼" }
];

const STATUS_FILTERS = [
  { id: "all", label: "All" },
  { id: "sent", label: "Sent" },
  { id: "opened", label: "Opened" },
  { id: "replied", label: "Replied" },
  { id: "bounced", label: "Bounced" },
  { id: "failed", label: "Failed" }
];

function UnifiedInbox({ campaignId, fetchApi }) {
  const [activities, setActivities] = useState([]);
  const [channelFilter, setChannelFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [expandedActivity, setExpandedActivity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadActivities();
  }, [campaignId, channelFilter, statusFilter]);

  const loadActivities = async () => {
    setLoading(true);
    setError("");

    try {
      let endpoint = `/api/inbox?limit=50`;
      if (campaignId) endpoint += `&campaign_id=${campaignId}`;
      if (channelFilter !== "all") endpoint += `&channel=${channelFilter}`;
      if (statusFilter !== "all") endpoint += `&status=${statusFilter}`;

      const data = await fetchApi(endpoint);
      setActivities(data.activities || []);
    } catch (err) {
      setError(err.message || "Failed to load inbox");
      setActivities([]);
    } finally {
      setLoading(false);
    }
  };

  const loadActivityDetails = async (activityId) => {
    try {
      const data = await fetchApi(`/api/inbox/${activityId}`);
      setExpandedActivity(data);
    } catch (err) {
      setError(err.message || "Failed to load activity details");
    }
  };

  const getChannelIcon = (channel) => {
    switch (channel) {
      case "email": return "📧";
      case "call": return "📞";
      case "linkedin": return "💼";
      default: return "📥";
    }
  };

  const getStatusBadge = (status) => {
    const classes = `status-badge status-${status}`;
    return <span className={classes}>{status}</span>;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const handleActivityClick = (activity) => {
    if (expandedActivity?.id === activity.id) {
      setExpandedActivity(null);
    } else {
      loadActivityDetails(activity.id);
    }
  };

  return (
    <div className="unified-inbox">
      <div className="inbox-header">
        <div>
          <h2>Inbox</h2>
          <p className="muted">All outreach activity across channels</p>
        </div>
        <button className="btn-secondary" onClick={loadActivities}>
          Refresh
        </button>
      </div>

      <div className="inbox-filters">
        <div className="channel-filters">
          {CHANNEL_FILTERS.map(filter => (
            <button
              key={filter.id}
              className={`filter-button ${channelFilter === filter.id ? "active" : ""}`}
              onClick={() => setChannelFilter(filter.id)}
            >
              <span className="filter-icon">{filter.icon}</span>
              {filter.label}
            </button>
          ))}
        </div>

        <div className="status-filters">
          {STATUS_FILTERS.map(filter => (
            <button
              key={filter.id}
              className={`filter-pill ${statusFilter === filter.id ? "active" : ""}`}
              onClick={() => setStatusFilter(filter.id)}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}

      {loading ? (
        <div className="inbox-loading">Loading activities...</div>
      ) : (
        <div className="activity-timeline">
          {activities.length === 0 ? (
            <div className="inbox-empty">
              <p className="muted">No activities found. Start a sequence to see activity here.</p>
            </div>
          ) : (
            activities.map((activity) => (
              <div
                key={activity.id}
                className={`activity-card ${expandedActivity?.id === activity.id ? "expanded" : ""}`}
                onClick={() => handleActivityClick(activity)}
              >
                <div className="activity-header">
                  <div className="activity-meta">
                    <span className="activity-icon">{getChannelIcon(activity.channel)}</span>
                    <div className="activity-info">
                      <strong>{activity.recipient_name || activity.recipient_email}</strong>
                      <span className="activity-company">{activity.company_name}</span>
                    </div>
                  </div>
                  <div className="activity-status-time">
                    {getStatusBadge(activity.status)}
                    <span className="activity-time">{formatTimestamp(activity.timestamp)}</span>
                  </div>
                </div>

                <div className="activity-summary">
                  {activity.channel === "email" && activity.subject && (
                    <p className="activity-subject">{activity.subject}</p>
                  )}
                  {activity.channel === "call" && (
                    <p className="activity-subject">Phone call ({activity.duration || "0:00"})</p>
                  )}
                  {activity.channel === "linkedin" && (
                    <p className="activity-subject">{activity.linkedin_type === "connect" ? "Connection request" : "LinkedIn message"}</p>
                  )}
                  {activity.preview && (
                    <p className="activity-preview">{activity.preview}</p>
                  )}
                </div>

                {expandedActivity?.id === activity.id && expandedActivity.details && (
                  <div className="activity-details">
                    <div className="activity-divider"></div>

                    {expandedActivity.details.body_html && (
                      <div className="activity-body">
                        <div
                          className="activity-html"
                          dangerouslySetInnerHTML={{ __html: expandedActivity.details.body_html }}
                        />
                      </div>
                    )}

                    {expandedActivity.details.body_plain && !expandedActivity.details.body_html && (
                      <div className="activity-body">
                        <pre className="activity-plain">{expandedActivity.details.body_plain}</pre>
                      </div>
                    )}

                    {expandedActivity.details.call_transcript && (
                      <div className="activity-body">
                        <h4>Call Transcript</h4>
                        <p>{expandedActivity.details.call_transcript}</p>
                      </div>
                    )}

                    {expandedActivity.details.call_recording_url && (
                      <div className="activity-recording">
                        <audio controls src={expandedActivity.details.call_recording_url}>
                          Your browser does not support the audio element.
                        </audio>
                      </div>
                    )}

                    {expandedActivity.details.linkedin_message && (
                      <div className="activity-body">
                        <p>{expandedActivity.details.linkedin_message}</p>
                      </div>
                    )}

                    <div className="activity-metadata">
                      <div className="metadata-row">
                        <span className="metadata-label">Sent from:</span>
                        <span>{expandedActivity.details.sender_email}</span>
                      </div>
                      {expandedActivity.details.sequence_name && (
                        <div className="metadata-row">
                          <span className="metadata-label">Sequence:</span>
                          <span>{expandedActivity.details.sequence_name}</span>
                        </div>
                      )}
                      <div className="metadata-row">
                        <span className="metadata-label">Sent at:</span>
                        <span>{new Date(activity.timestamp).toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default UnifiedInbox;

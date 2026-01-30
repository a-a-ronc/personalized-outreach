function SequenceSettings({ campaignId, fetchApi }) {
  return (
    <div className="sequence-settings apollo-card">
      <div className="card-header">
        <h2 className="card-title">Sequence Settings</h2>
      </div>
      <div className="card-content">
        <p className="muted">Sequence configuration options will appear here.</p>
        <p className="muted">Coming soon: Send windows, rate limiting, stop conditions, and auto-replies.</p>
      </div>
    </div>
  );
}

export default SequenceSettings;

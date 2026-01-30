function SequenceActivity({ campaignId, fetchApi }) {
  return (
    <div className="sequence-activity apollo-card">
      <div className="card-header">
        <h2 className="card-title">Activity Timeline</h2>
      </div>
      <div className="card-content">
        <p className="muted">Sequence activity timeline will appear here.</p>
        <p className="muted">Coming soon: Email sends, opens, clicks, replies, calls, and LinkedIn activity.</p>
      </div>
    </div>
  );
}

export default SequenceActivity;

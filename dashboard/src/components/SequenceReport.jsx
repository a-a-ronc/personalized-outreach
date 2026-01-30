function SequenceReport({ campaignId, fetchApi }) {
  return (
    <div className="sequence-report apollo-card">
      <div className="card-header">
        <h2 className="card-title">Sequence Analytics</h2>
      </div>
      <div className="card-content">
        <p className="muted">Sequence-specific analytics will appear here.</p>
        <p className="muted">Coming soon: Open rates, reply rates, conversion metrics, and A/B test results.</p>
      </div>
    </div>
  );
}

export default SequenceReport;

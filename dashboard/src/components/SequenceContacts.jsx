function SequenceContacts({ campaignId, fetchApi }) {
  return (
    <div className="sequence-contacts apollo-card">
      <div className="card-header">
        <h2 className="card-title">Contacts in Sequence</h2>
      </div>
      <div className="card-content">
        <p className="muted">Leads enrolled in this sequence will appear here.</p>
        <p className="muted">Coming soon: Lead status tracking, sequence progress, and enrollment management.</p>
      </div>
    </div>
  );
}

export default SequenceContacts;

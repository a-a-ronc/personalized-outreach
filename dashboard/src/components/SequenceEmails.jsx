function SequenceEmails({ campaignId, fetchApi }) {
  return (
    <div className="sequence-emails apollo-card">
      <div className="card-header">
        <h2 className="card-title">Sent Emails</h2>
      </div>
      <div className="card-content">
        <p className="muted">Emails sent from this sequence will appear here.</p>
        <p className="muted">Coming soon: Email list with open/click/reply tracking.</p>
      </div>
    </div>
  );
}

export default SequenceEmails;

import json
import time
from datetime import datetime, timedelta
from lead_registry import get_connection, utc_now, parse_timestamp, log_outreach
from voice_calls import schedule_bland_ai_call
from linkedin_automation import send_connection_request, send_linkedin_message
from config import Config
import uuid
import logging

logger = logging.getLogger(__name__)


def create_sequence(campaign_id, name, steps, sender_email=None):
    """
    Create a new sequence.

    Args:
        campaign_id: Campaign ID
        name: Sequence name
        steps: List of step dicts with structure:
            {
                'type': 'email' | 'call' | 'linkedin_connect' | 'linkedin_message' | 'wait',
                'delay_days': int,
                'template': str (for email),
                'script': str (for call),
                'message': str (for LinkedIn)
            }
        sender_email: Email of the sequence owner/sender

    Returns:
        sequence_id
    """
    sequence_id = str(uuid.uuid4())
    now = utc_now()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO sequences (id, campaign_id, name, steps, sender_email, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sequence_id, campaign_id, name, json.dumps(steps), sender_email or "", now, now))

        # Insert individual steps for easier querying
        for idx, step in enumerate(steps):
            conn.execute("""
                INSERT INTO sequence_steps (sequence_id, step_order, step_type, delay_days, channel, template_data, conditions, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sequence_id,
                idx,
                step['type'],
                step.get('delay_days', 0),
                step.get('type', 'email'),
                json.dumps(step),
                json.dumps(step.get('conditions', {})),
                now
            ))

    return sequence_id


def load_sequence(sequence_id):
    """Load sequence by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sequences WHERE id = ?", (sequence_id,)).fetchone()

    if row:
        seq_dict = dict(row)
        seq_dict['steps'] = json.loads(seq_dict['steps'])
        return seq_dict
    return None


def load_sequence_by_campaign(campaign_id):
    """Load sequence for a campaign."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sequences WHERE campaign_id = ? ORDER BY created_at DESC LIMIT 1", (campaign_id,)).fetchone()

    if row:
        seq_dict = dict(row)
        seq_dict['steps'] = json.loads(seq_dict['steps'])
        return seq_dict
    return None


def enroll_lead_in_sequence(person_key, campaign_id, sequence_id):
    """
    Enroll a lead in a sequence.
    Creates initial outreach_log entry with first step scheduled.

    Returns:
        outreach_log_id
    """
    sequence = load_sequence(sequence_id)
    if not sequence or len(sequence['steps']) == 0:
        raise Exception("Invalid sequence")

    first_step = sequence['steps'][0]
    now = datetime.now()

    # Calculate next action time
    if first_step.get('delay_days', 0) > 0:
        next_action_at = now + timedelta(days=first_step['delay_days'])
    else:
        next_action_at = now

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO outreach_log (person_key, campaign_id, sequence_step, sent_at, status, channel, next_action_at, action_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            person_key,
            campaign_id,
            0,  # First step
            utc_now(),
            'pending',
            first_step['type'],
            next_action_at.isoformat(),
            json.dumps(first_step)
        ))

        row = conn.execute("SELECT last_insert_rowid() as id").fetchone()
        return row['id']


def process_sequences():
    """
    Main orchestration loop.
    Find and execute pending sequence steps.
    """
    conn = get_connection()

    # Find all leads with pending sequence steps that are due
    pending = conn.execute("""
        SELECT ol.*, lp.*, lc.name as company_name
        FROM outreach_log ol
        JOIN leads_people lp ON ol.person_key = lp.person_key
        LEFT JOIN leads_company lc ON lp.company_key = lc.company_key
        WHERE ol.next_action_at <= ? AND ol.status = 'pending'
        ORDER BY ol.next_action_at ASC
    """, (utc_now(),)).fetchall()

    logger.info(f"Processing {len(pending)} pending sequence steps")

    for record in pending:
        try:
            execute_sequence_step(dict(record))
        except Exception as e:
            logger.error(f"Error executing step for {record['email']}: {e}")
            # Mark as failed
            conn.execute("""
                UPDATE outreach_log
                SET status = 'failed'
                WHERE id = ?
            """, (record['id'],))

    conn.close()


def execute_sequence_step(record):
    """Execute next step for a lead."""
    action_metadata = json.loads(record.get('action_metadata', '{}'))
    step_type = action_metadata.get('type')

    logger.info(f"Executing {step_type} step for {record['email']}")

    if step_type == 'email':
        send_email_step(record, action_metadata)
    elif step_type == 'call':
        initiate_call_step(record, action_metadata)
    elif step_type == 'linkedin_connect':
        send_linkedin_connection_step(record, action_metadata)
    elif step_type == 'linkedin_message':
        send_linkedin_message_step(record, action_metadata)
    elif step_type == 'wait':
        # Wait steps don't do anything, just schedule next step
        pass

    # Mark step complete and schedule next step
    schedule_next_step(record)


def send_email_step(record, action_metadata):
    """Send email via SendGrid."""
    from personalization_engine import generate_email_by_mode
    from signature_manager import get_default_signature
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    from warmup_controller import WarmupController

    logger.info(f"Sending email to {record['email']}")

    # Load campaign to get personalization mode
    campaign_id = record['campaign_id']

    # Import load_json from backend.app
    import sys
    from pathlib import Path
    BASE_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(BASE_DIR / "backend"))

    try:
        from app import load_json
        campaigns_data = load_json()
        campaigns = {c['id']: c for c in campaigns_data.get('campaigns', [])}
        campaign = campaigns.get(campaign_id)

        if not campaign:
            logger.error(f"Campaign {campaign_id} not found")
            conn = get_connection()
            conn.execute("UPDATE outreach_log SET status = 'failed' WHERE id = ?", (record['id'],))
            conn.close()
            return

        # Get personalization mode
        settings = campaign.get('settings', {})
        personalization_mode = settings.get('personalization_mode', 'signal_based')

        # Build lead data
        lead_data = {
            'Company': record.get('company_name', ''),
            'company_name': record.get('company_name', ''),
            'first_name': record.get('first_name', ''),
            'First Name': record.get('first_name', ''),
            'title': record.get('title', ''),
            'Job title': record.get('title', '')
        }

        apollo_data = {
            'industry': record.get('industry', ''),
            'employee_count': str(record.get('employee_count', '')),
            'technologies': record.get('technologies', ''),
            'job_postings_relevant': record.get('job_postings_relevant', 0)
        }

        # Generate personalization
        personalization, success = generate_email_by_mode(
            personalization_mode,
            lead_data,
            apollo_data,
            {'strategy': campaign.get('strategy', 'conventional'), 'pain_theme': 'throughput'}
        )

        if not success:
            personalization = f"Hi {record.get('first_name', 'there')}, I wanted to reach out about warehouse automation opportunities."

        # Get template
        template_name = action_metadata.get('template', 'email_1')
        sequence = campaign.get('sequence', {})
        email_template = sequence.get(template_name, {}).get('variant_a', {})

        subject = email_template.get('subject', 'Warehouse Automation Opportunity')
        body_template = email_template.get('body', '{{personalization_sentence}}')

        # Replace variables
        body_html = body_template.replace('{{personalization_sentence}}', personalization)
        body_html = body_html.replace('{{first_name}}', record.get('first_name', ''))
        body_html = body_html.replace('{{company_name}}', record.get('company_name', ''))

        # Add signature
        signature = get_default_signature()
        if signature:
            body_html += f"\n\n{signature['html_content']}"

        # Send via SendGrid
        sg = SendGridAPIClient(api_key=Config.SENDGRID_API_KEY)
        sender_profile = Config.get_sender_profile(0)
        sender_email = sender_profile['email']

        # Check warmup limits before sending
        warmup_controller = WarmupController()
        can_send, sends_today, daily_limit = warmup_controller.can_send(sender_email)

        if not can_send:
            logger.warning(
                f"Daily limit reached for {sender_email}: {sends_today}/{daily_limit}. "
                f"Skipping send to {record['email']}"
            )
            conn = get_connection()
            conn.execute("""
                UPDATE outreach_log
                SET status = 'throttled',
                    next_action_at = datetime('now', '+1 day')
                WHERE id = ?
            """, (record['id'],))
            conn.close()
            return

        mail = Mail(
            from_email=Email(sender_profile['email'], sender_profile['full_name']),
            to_emails=To(record['email']),
            subject=subject,
            html_content=Content("text/html", body_html)
        )

        response = sg.client.mail.send.post(request_body=mail.get())

        if response.status_code == 202:
            # Update outreach_log
            conn = get_connection()
            conn.execute("""
                UPDATE outreach_log
                SET status = 'sent', sent_at = ?
                WHERE id = ?
            """, (utc_now(), record['id']))
            conn.close()

            # Record send for warmup tracking
            warmup_controller.record_send(
                sender_email=sender_email,
                recipient_email=record['email'],
                send_type='campaign'
            )

            logger.info(f"Email sent successfully to {record['email']} (warmup: {sends_today + 1}/{daily_limit})")
        else:
            logger.error(f"SendGrid returned status {response.status_code}")
            conn = get_connection()
            conn.execute("UPDATE outreach_log SET status = 'failed' WHERE id = ?", (record['id'],))
            conn.close()

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        conn = get_connection()
        conn.execute("UPDATE outreach_log SET status = 'failed' WHERE id = ?", (record['id'],))
        conn.close()


def initiate_call_step(record, action_metadata):
    """Initiate AI call via Bland.ai."""
    script = action_metadata.get('script', '')

    if not script:
        logger.warning(f"No script provided for call step")
        return

    # Format phone number to E.164
    phone = record.get('phone', '')
    if not phone:
        logger.warning(f"No phone number for {record['email']}")
        conn = get_connection()
        conn.execute("UPDATE outreach_log SET status = 'skipped' WHERE id = ?", (record['id'],))
        conn.close()
        return

    # Schedule call via Bland.ai
    try:
        call_id = schedule_bland_ai_call(
            phone_number=phone,
            script=script,
            lead_data={
                'first_name': record['first_name'],
                'company_name': record.get('company_name', ''),
                'title': record['title']
            }
        )

        # Update outreach_log with call ID
        conn = get_connection()
        action_metadata['call_id'] = call_id
        conn.execute("""
            UPDATE outreach_log
            SET status = 'call_initiated',
                action_metadata = ?
            WHERE id = ?
        """, (json.dumps(action_metadata), record['id']))
        conn.close()

        logger.info(f"Initiated call {call_id} to {phone}")

    except Exception as e:
        logger.error(f"Failed to initiate call: {e}")
        conn = get_connection()
        conn.execute("UPDATE outreach_log SET status = 'failed' WHERE id = ?", (record['id'],))
        conn.close()


def send_linkedin_connection_step(record, action_metadata):
    """Send LinkedIn connection request."""
    linkedin_url = record.get('linkedin_url_norm', '')
    message = action_metadata.get('message', '')

    if not linkedin_url:
        logger.warning(f"No LinkedIn URL for {record['email']}")
        conn = get_connection()
        conn.execute("UPDATE outreach_log SET status = 'skipped' WHERE id = ?", (record['id'],))
        conn.close()
        return

    # Check rate limit
    if not check_linkedin_rate_limit():
        logger.warning("LinkedIn rate limit reached for today")
        # Reschedule for tomorrow
        conn = get_connection()
        tomorrow = datetime.now() + timedelta(days=1)
        conn.execute("""
            UPDATE outreach_log
            SET next_action_at = ?
            WHERE id = ?
        """, (tomorrow.isoformat(), record['id']))
        conn.close()
        return

    try:
        success = send_connection_request(linkedin_url, message)

        conn = get_connection()
        if success:
            conn.execute("""
                UPDATE outreach_log
                SET status = 'linkedin_sent'
                WHERE id = ?
            """, (record['id'],))

            # Update person record
            conn.execute("""
                UPDATE leads_people
                SET linkedin_connection_status = 'pending',
                    linkedin_connected_at = ?
                WHERE person_key = ?
            """, (utc_now(), record['person_key']))

            logger.info(f"Sent LinkedIn connection to {record['first_name']} {record['last_name']}")
        else:
            conn.execute("UPDATE outreach_log SET status = 'linkedin_failed' WHERE id = ?", (record['id'],))

        conn.close()

    except Exception as e:
        logger.error(f"LinkedIn connection failed: {e}")
        conn = get_connection()
        conn.execute("UPDATE outreach_log SET status = 'failed' WHERE id = ?", (record['id'],))
        conn.close()


def send_linkedin_message_step(record, action_metadata):
    """Send LinkedIn message to existing connection."""
    linkedin_url = record.get('linkedin_url_norm', '')
    message = action_metadata.get('message', '')

    if not linkedin_url:
        logger.warning(f"No LinkedIn URL for {record['email']}")
        conn = get_connection()
        conn.execute("UPDATE outreach_log SET status = 'skipped' WHERE id = ?", (record['id'],))
        conn.close()
        return

    # Check rate limit
    if not check_linkedin_rate_limit():
        logger.warning("LinkedIn rate limit reached")
        conn = get_connection()
        tomorrow = datetime.now() + timedelta(days=1)
        conn.execute("UPDATE outreach_log SET next_action_at = ? WHERE id = ?", (tomorrow.isoformat(), record['id']))
        conn.close()
        return

    try:
        success = send_linkedin_message(linkedin_url, message)

        conn = get_connection()
        if success:
            conn.execute("UPDATE outreach_log SET status = 'linkedin_message_sent' WHERE id = ?", (record['id'],))
            logger.info(f"Sent LinkedIn message to {record['first_name']} {record['last_name']}")
        else:
            conn.execute("UPDATE outreach_log SET status = 'linkedin_failed' WHERE id = ?", (record['id'],))

        conn.close()

    except Exception as e:
        logger.error(f"LinkedIn message failed: {e}")
        conn = get_connection()
        conn.execute("UPDATE outreach_log SET status = 'failed' WHERE id = ?", (record['id'],))
        conn.close()


def schedule_next_step(record):
    """Calculate and schedule next sequence step."""
    campaign_id = record['campaign_id']
    current_step_idx = record['sequence_step']

    # Load sequence
    sequence = load_sequence_by_campaign(campaign_id)
    if not sequence:
        logger.warning(f"No sequence found for campaign {campaign_id}")
        return

    # Check if there are more steps
    if current_step_idx + 1 >= len(sequence['steps']):
        # Sequence complete
        conn = get_connection()
        conn.execute("""
            UPDATE outreach_log
            SET status = 'completed'
            WHERE id = ?
        """, (record['id'],))
        conn.close()
        logger.info(f"Sequence completed for {record['email']}")
        return

    # Get next step
    next_step = sequence['steps'][current_step_idx + 1]
    next_step_idx = current_step_idx + 1

    # Calculate next action time
    now = datetime.now()
    delay_days = next_step.get('delay_days', 0)
    next_action_at = now + timedelta(days=delay_days)

    # Update outreach_log
    conn = get_connection()
    conn.execute("""
        UPDATE outreach_log
        SET next_action_at = ?,
            sequence_step = ?,
            action_metadata = ?,
            status = 'pending',
            channel = ?
        WHERE id = ?
    """, (
        next_action_at.isoformat(),
        next_step_idx,
        json.dumps(next_step),
        next_step['type'],
        record['id']
    ))
    conn.close()

    logger.info(f"Scheduled next step ({next_step['type']}) for {record['email']} at {next_action_at}")


def check_linkedin_rate_limit():
    """Ensure we don't exceed LinkedIn daily limits."""
    conn = get_connection()
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    count_result = conn.execute("""
        SELECT COUNT(*) as count FROM outreach_log
        WHERE channel IN ('linkedin_connect', 'linkedin_message')
        AND sent_at >= ?
        AND status IN ('linkedin_sent', 'linkedin_message_sent')
    """, (today_start,)).fetchone()

    conn.close()

    count = count_result['count'] if count_result else 0
    max_connections = Config.LINKEDIN_MAX_CONNECTIONS_PER_DAY

    return count < max_connections


def get_sequence_status(sequence_id):
    """Get status of all leads in a sequence."""
    conn = get_connection()

    stats = conn.execute("""
        SELECT
            status,
            COUNT(*) as count
        FROM outreach_log
        WHERE campaign_id IN (SELECT campaign_id FROM sequences WHERE id = ?)
        GROUP BY status
    """, (sequence_id,)).fetchall()

    conn.close()

    return {row['status']: row['count'] for row in stats}

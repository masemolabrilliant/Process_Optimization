# src/email_sender.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict

def send_email(to_address: str, subject: str, body: str, sender: str = "lads22359@gmail.com"):
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_address
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    gmail_user = sender
    gmail_password = 'udoc jpes dnof azku'  # App password, not Gmail login password

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
            print(f"Email sent to {to_address}")
    except Exception as e:
        print(f"Failed to send email to {to_address}: {e}")

def notify_technicians(schedule: List[Dict], technicians: List[Dict]):
    tech_lookup = {tech['tech_id']: tech for tech in technicians}

    for job in schedule:
        for tech_id in job.get('assigned_technicians', []):
            tech = tech_lookup.get(tech_id)
            if tech and 'email' in tech:
                subject = f"Job Assignment: {job['job_id']}"
                body = (
                    f"Hello {tech.get('name', tech_id)},\n\n"
                    f"You have been assigned to the following job:\n"
                    f"Job ID: {job['job_id']}\n"
                    f"Equipment ID: {job['equipment_id']}\n"
                    f"Start Time: {job['scheduled_start_time']}\n"
                    f"End Time: {job['scheduled_end_time']}\n\n"
                    "Please be prepared and confirm availability.\n\n"
                    "Thank you."
                )
                send_email(tech['email'], subject, body)

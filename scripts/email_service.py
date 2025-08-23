from __future__ import print_function
import os.path
import base64
import json
from pathlib import Path
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes define the level of access we need (sending emails)
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

master_log_path = Path("agent_logs/master_log.json")


# ---- Step 1: Authenticate and Get Gmail Service ----
def gmail_service():
    creds = None
    # If token.json exists, load it (this avoids logging in every time)
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If no (or invalid) creds, prompt user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)  # opens browser for login
        # Save token for future runs
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

# ---- Step 2: Function to Send Email ----
def send_email(to, subject):
    service = gmail_service()
    data = get_latest_log()
    html_content = get_html_content(data)
    message = MIMEText(html_content, "html")
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    send_message = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"✅ Message sent to: {to}")


# ---- Step 4: Your Final HTML Template ----
def get_html_content(data):
    html_content = f"""
    <html>
    <body style="font-family:Segoe UI, Roboto, Arial, sans-serif; background:#f4f6f9; padding:30px; color:#333;">
        <div style="max-width:850px; margin:auto; background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 6px 16px rgba(0,0,0,0.12);">
        
        <!-- Header -->
        <div style="background:linear-gradient(90deg, #2d89ef, #1b6ec2); color:white; padding:25px 30px;">
            <h2 style="margin:0; font-weight:500; text-align: center">⚡ PatchIQ.AI – Error Fix Report</h2>
        </div>

        <!-- Error Summary -->
        <div style="padding:25px;">
            <h3 style="color:#2d89ef; margin-top:0; font-size:18px;">📌 Error Summary</h3>
            <table style="width:100%; border-collapse:separate; border-spacing:0 8px; font-size:14px;">
            <tr>
                <td style="background:#f9f9f9; padding:10px 14px; font-weight:bold; border-radius:6px 0 0 6px; width:25%;">Error File:</td>
                <td style="background:#f9f9f9; padding:10px 14px; border-radius:0 6px 6px 0;">{data['error_file']}</td>
            </tr>
            <tr>
                <td style="background:#f9f9f9; padding:10px 14px; font-weight:bold; border-radius:6px 0 0 6px; width:25%;">Branch:</td>
                <td style="background:#f9f9f9; padding:10px 14px; border-radius:0 6px 6px 0;">{data['branch_name']}</td>
            </tr>
            <tr>
                <td style="background:#f9f9f9; padding:10px 14px; font-weight:bold; border-radius:6px 0 0 6px;">Pull Request Link:</td>
                <td style="background:#f9f9f9; padding:10px 14px; border-radius:0 6px 6px 0;">
                <a href="{data['pr_url']}" style="color:#2d89ef; text-decoration:none; font-weight:bold;">🔗 View PR</a>
                </td>
            </tr>
            </table>

            <!-- Traceback -->
            <h3 style="color:#2d89ef; margin-top:30px; font-size:18px;">📝 Traceback</h3>
            <div style="background:#1e1e1e; color:#e8e8e8; border-radius:8px; padding:14px; font-family:Consolas, monospace; font-size:13px; white-space:pre-wrap; line-height:1.5; overflow-x:auto;">
    {data['trace']}
            </div>

            <!-- Root Cause -->
            <h3 style="color:#2d89ef; margin-top:30px; font-size:18px;">⚠️ Root Cause</h3>
            <div style="background:#fff8e1; border-left:6px solid #f1c40f; padding:14px; border-radius:6px; font-size:14px; line-height:1.6;">
            {data['root_cause']}
            </div>

            <!-- Proposed Fix -->
            <h3 style="color:#2d89ef; margin-top:30px; font-size:18px;">✅ Proposed Fix</h3>
            <div style="background:#e8f5e9; border-left:6px solid #27ae60; padding:14px; border-radius:6px; font-size:14px; line-height:1.6;">
            {data['proposed_fix']}
            </div>
        </div>

        <!-- Footer -->
        <div style="background:#f9f9f9; padding:18px; text-align:center; font-size:12px; color:#666; border-top:1px solid #eee;">
            This is an automated notification from <b>PatchIQ.AI</b>. Please review the changes at your earliest convenience.
        </div>
        </div>
    </body>
    </html>
    """

    return html_content


def get_latest_log():
    if master_log_path.exists():
        logs = json.loads(master_log_path.read_text(encoding="utf-8"))
        if logs:
            data = logs[-1]
        else:
            data = {}
            print("No records found in master_log.json")
    else:
        data = {}
        print("master_log.json does not exist")

    return data
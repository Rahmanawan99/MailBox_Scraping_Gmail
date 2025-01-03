import os
import base64
import re
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_service():
    """Authenticate and return the Gmail API service."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

#This function acts like a log when scraping multiple files - you may use logs to verify your progress
def read_downloaded_ids(log_file='downloaded_ids.txt'):
    """Read the list of already downloaded message IDs."""
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            return set(f.read().splitlines())  
    return set()

def write_downloaded_id(msg_id, log_file='downloaded_ids.txt'):
    """Append the message ID to the log file after scraping."""
    with open(log_file, 'a') as f:
        f.write(msg_id + '\n')

#This function is a fail-safe if downloads fail
def download_attachment_with_retries(service, user_id, msg_id, att_id, retries=3, delay=2):
    """Try downloading an attachment with retries."""
    attempt = 0
    while attempt < retries:
        try:
            attachment = service.users().messages().attachments().get(
                userId=user_id, messageId=msg_id, id=att_id).execute()
            return attachment['data']
        except Exception as e:
            print(f"Error on attempt {attempt+1}: {e}")
            time.sleep(delay)  # Wait before retrying
            attempt += 1
    return None  # Return None if all retries fail

def extract_pdfs(service, user_id='me'):
    """Extract PDFs from the 'Sent' folder."""
    try:
        #Add your query here like you will do on search bar on the gmail mailbox
        query = 'to:youremail@domain.com from:@domain.com has:attachment filename:pdf -is:reply after:2024/09/01'

        # Read the set of already downloaded message IDs
        downloaded_ids = read_downloaded_ids()

        messages = []
        results = service.users().messages().list(userId=user_id, q=query).execute()

        if 'messages' in results:
            messages.extend(results['messages'])

        # this goes to next page
        while 'nextPageToken' in results:
            page_token = results['nextPageToken']
            results = service.users().messages().list(userId=user_id, q=query, pageToken=page_token).execute()
            messages.extend(results['messages'])  # Add more messages to the list

        if not messages:
            print("No PDF attachments found in 'Sent' folder.")
            return

        print(f"Found {len(messages)} emails with PDFs.")

        for msg in messages:
            msg_id = msg['id']
            if msg_id in downloaded_ids:
                print(f"Skipping already downloaded email with ID: {msg_id}")
                continue  # Skip already downloaded messages

            message = service.users().messages().get(userId=user_id, id=msg_id).execute()
            for part in message['payload'].get('parts', []):
                if part['filename'] and part['filename'].endswith('.pdf'):
                    print(f"Found PDF: {part['filename']}")
                    data = part['body'].get('data')

                    if not data:
                        att_id = part['body'].get('attachmentId')
                        if att_id:
                            print(f"Attachment ID: {att_id}")  # Log here
                            data = download_attachment_with_retries(service, user_id, msg_id, att_id)
                            if not data:
                                print(f"Failed to download PDF after retries: {part['filename']}")
                        else:
                            print(f"Attachment ID missing for: {part['filename']}")

                    if data:
                        file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
                        path = os.path.join('downloads', part['filename'])
                        os.makedirs('downloads', exist_ok=True)
                        with open(path, 'wb') as f:
                            f.write(file_data)
                        print(f"Saved PDF: {path}")
                        
                        write_downloaded_id(msg_id)

    except HttpError as error:
        print(f'An error occurred: {error}')

if __name__ == '__main__':
    service = get_service()
    extract_pdfs(service)

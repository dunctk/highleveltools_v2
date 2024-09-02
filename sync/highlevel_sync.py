import os
import requests
from dotenv import load_dotenv
from django.conf import settings
from .models import Contact, ContactCustomField, CustomField
from tqdm import tqdm

load_dotenv()

# Load HighLevel API key from environment variable or settings
HL_API_KEY = os.environ['HIGHLEVEL_API_KEY']

# HighLevel API base URL
HL_BASE_URL = 'https://rest.gohighlevel.com/v1'

def check_api_connection():
    """Check if the API connection is working"""
    
    headers = {
        'Authorization': f'Bearer {HL_API_KEY}',
        'Content-Type': 'application/json'
    }
    url = f"{HL_BASE_URL}/locations/"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("API connection successful!")
        return True
    else:
        print(f"API connection failed. Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return False

def sync_contact_to_highlevel(contact):
    """Sync a single contact to HighLevel"""
    # Check API connection first
    #if not check_api_connection():
    #    return

    headers = {
        'Authorization': f'Bearer {HL_API_KEY}',
        'Content-Type': 'application/json'
    }

    # Prepare contact data
    contact_data = {
        'firstName': contact.first_name,
        'lastName': contact.last_name,
        'email': contact.email,
    }

    # Add custom fields
    custom_fields = {}
    for ccf in ContactCustomField.objects.filter(contact=contact):
        custom_field = ccf.custom_field
        #print(ccf.custom_field)
        #print(ccf.value)
        custom_fields[custom_field.ac_title] = ccf.value
    
    
    if custom_fields:
        contact_data['customFields'] = custom_fields

    # Check if contact already exists in HighLevel
    if contact.hl_id:
        # Update existing contact
        url = f"{HL_BASE_URL}/contacts/{contact.hl_id}"
        response = requests.put(url, json=contact_data, headers=headers)
    else:
        # Create new contact
        url = f"{HL_BASE_URL}/contacts"
        response = requests.post(url, json=contact_data, headers=headers)

    if response.status_code in (200, 201):
        result = response.json()
        if not contact.hl_id:
            contact.hl_id = result['contact']['id']
            contact.save()
        #print(f"Successfully synced contact: {contact.email}")
    else:
        print(f"Failed to sync contact: {contact.email}. Status code: {response.status_code}")
        print(f"Response: {response.text}")

def sync_all_contacts_to_highlevel(limit=None, test_mode=False):
    """Sync all contacts to HighLevel"""
    contacts = Contact.objects.all()
    if limit:
        contacts = contacts[:limit]
    
    for contact in tqdm(contacts):
        if test_mode:
            print(f"Syncing contact to HighLevel: {contact.first_name} {contact.last_name} (ID: {contact.ac_id})")
        sync_contact_to_highlevel(contact)
    
    return contacts


if __name__ == "__main__":
    sync_all_contacts_to_highlevel()

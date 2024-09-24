import os
import requests
import requests_cache
from dotenv import load_dotenv
from tqdm import tqdm
from datetime import timedelta
import json
from django.utils.dateparse import parse_datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
import time
from requests_ratelimiter import LimiterSession
import logging
from django.db import transaction
from django.utils import timezone
from celery import shared_task

# Move the imports that depend on Django here
from sync.models import Contact, CustomField, ContactCustomField, Deal, DealStage, PipeLine, SyncLog
from ..highlevel_sync import check_api_connection, sync_contact_to_highlevel

# Load environment variables and set up request caching
load_dotenv()
requests_cache.install_cache('activecampaign_cache', expire_after=timedelta(hours=24))

# Create a rate-limited session that works with the cache
class CachedLimiterSession(LimiterSession):
    def send(self, request, **kwargs):
        with requests_cache.disabled():
            return super().send(request, **kwargs)

# Create the session with rate limiting
session = CachedLimiterSession(per_second=5, concurrent=1)  # Limit to 5 requests per second and 1 concurrent request

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def make_request(method, url, use_retry=True, **kwargs):
    try:
        response = session.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        if use_retry:
            logger.warning(f"Request failed: {str(e)}. Retrying...")
            raise
        else:
            logger.warning(f"Request failed: {str(e)}. Skipping...")
            return None

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
def make_request_with_retry(method, url, **kwargs):
    return make_request(method, url, use_retry=True, **kwargs)

def get_activecampaign_contacts_page(base_url, headers, params, use_retry=True):
    try:
        if use_retry:
            response = make_request_with_retry('GET', f"{base_url}/contacts", headers=headers, params=params)
        else:
            response = make_request('GET', f"{base_url}/contacts", use_retry=False, headers=headers, params=params)
        
        if response is None:
            return []
        
        contacts_data = response.json()
        contacts = contacts_data.get("contacts", [])
        
        for contact in contacts:
            # Fetch custom fields for each contact using the provided link
            field_values_link = next((link['href'] for link in contacts_data.get('links', []) if link['rel'] == 'fieldValues'), None)
            if field_values_link:
                custom_fields = get_contact_custom_fields(field_values_link, headers, use_retry)
                contact['custom_fields'] = custom_fields
            else:
                logger.warning(f"No fieldValues link found for contact {contact['id']}")
                contact['custom_fields'] = []
            
            # Fetch deals for each contact
            deals = get_contact_deals(base_url, headers, contact['id'], use_retry)
            contact['deals'] = deals
        
        return contacts
    except requests.exceptions.RequestException as e:
        logger.error(f"Error retrieving contacts: {str(e)}")
        return []

def get_contact_custom_fields(field_values_link, headers, use_retry=True):
    all_field_values = []
    
    while field_values_link:
        try:
            if use_retry:
                response = make_request_with_retry('GET', field_values_link, headers=headers)
            else:
                response = make_request('GET', field_values_link, use_retry=False, headers=headers)
            
            if response is None:
                break
            
            field_values_data = response.json()
            field_values = field_values_data.get("fieldValues", [])
            all_field_values.extend(field_values)
            
            # Check for the next page link
            field_values_link = next((link['href'] for link in field_values_data.get('links', []) if link['rel'] == 'next'), None)
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error retrieving custom fields: {str(e)}")
            break

    return all_field_values

def get_contact_deals(base_url, headers, contact_id, use_retry=True):
    try:
        if use_retry:
            response = make_request_with_retry('GET', f"{base_url}/deals?filters[contact_id]={contact_id}", headers=headers)
        else:
            response = make_request('GET', f"{base_url}/deals?filters[contact_id]={contact_id}", use_retry=False, headers=headers)
        
        if response is None:
            return []
        
        return response.json().get("deals", [])
    except requests.exceptions.RequestException as e:
        print(f"Error retrieving deals for contact {contact_id}: {str(e)}")
        return []

def process_contact(contact):
    with transaction.atomic():
        # Lock the contact object for update
        contact_obj = Contact.objects.select_for_update().filter(ac_id=contact['id']).first()
        
        if contact_obj:
            # Update existing contact
            contact_obj.email = contact.get('email')
            contact_obj.first_name = contact.get('firstName')
            contact_obj.last_name = contact.get('lastName')
            contact_obj.ac_json = json.dumps(contact)
            contact_obj.save()
        else:
            # Create new contact
            contact_obj = Contact.objects.create(
                ac_id=contact['id'],
                email=contact.get('email'),
                first_name=contact.get('firstName'),
                last_name=contact.get('lastName'),
                ac_json=json.dumps(contact)
            )

        # Process custom fields
        for field in contact.get('custom_fields', []):
            custom_field = CustomField.objects.select_for_update().get_or_create(
                ac_id=field['field'],
                defaults={
                    'type': field.get('fieldType', ''),
                    'ac_title': field.get('fieldTitle', ''),
                    'ac_json': json.dumps(field)
                }
            )[0]

            ContactCustomField.objects.update_or_create(
                contact=contact_obj,
                custom_field=custom_field,
                defaults={
                    'value': field.get('value', '')
                }
            )

        # Process deals
        for deal in contact.get('deals', []):
            # Fetch or create the pipeline
            pipeline = PipeLine.objects.select_for_update().get_or_create(
                ac_id=deal.get('pipeline') or deal.get('group') or deal.get('dealGroup'),
                defaults={
                    'name': deal.get('pipeline_title') or deal.get('group_title') or 'Unknown Pipeline',
                    'ac_json': json.dumps(deal.get('pipeline', {}))
                }
            )[0]

            # Fetch or create the deal stage
            stage = DealStage.objects.select_for_update().get_or_create(
                ac_id=deal.get('stage'),
                defaults={
                    'name': deal.get('stage_title', 'Unknown Stage'),
                    'pipeline': pipeline,
                    'ac_json': deal.get('stage', {})
                }
            )[0]

            Deal.objects.update_or_create(
                ac_id=deal['id'],
                defaults={
                    'contact': contact_obj,
                    'stage': stage,
                    'title': deal.get('title', 'Untitled Deal'),
                    'value': deal.get('value'),
                    'currency': deal.get('currency', 'USD'),
                    'created_date': parse_datetime(deal.get('cdate')),
                    'updated_date': parse_datetime(deal.get('mdate')),
                    'ac_json': json.dumps(deal)
                }
            )

    return contact_obj

def get_and_process_activecampaign_contacts(limit=None):
    base_url = os.environ.get("ACTIVECAMPAIGN_URL")
    if not base_url.startswith("https://"):
        base_url = f"https://{base_url}"
    base_url += ".api-us1.com/api/3"
    
    api_key = os.environ.get("ACTIVECAMPAIGN_KEY")
    
    headers = {
        "Api-Token": api_key,
        "Content-Type": "application/json"
    }
    
    try:
        initial_response = make_request('GET', f"{base_url}/contacts", headers=headers, params={"limit": 1})
        total_contacts = int(initial_response.json().get("meta", {}).get("total", 0))
    except requests.exceptions.RequestException as e:
        print(f"Error getting total contacts: {str(e)}")
        return 0
    
    if limit:
        total_contacts = min(limit, total_contacts)
    
    limit = 100
    num_pages = (total_contacts + limit - 1) // limit
    
    pbar = tqdm(total=total_contacts, desc="Processing contacts", unit="contact")
    
    processed_contacts = 0
    
    for i in range(num_pages):
        contacts = get_activecampaign_contacts_page(base_url, headers, {"limit": limit or 100, "offset": i * (limit or 100)})
        
        for contact in contacts:
            try:
                processed_contact = process_contact(contact) 
                processed_contacts += 1
                pbar.update(1)
            except Exception as e:
                logger.error(f"Error processing contact: {e}")
        
        if limit and processed_contacts >= limit:
            break
    
    pbar.close()
    
    return processed_contacts

def get_activecampaign_pipelines(base_url, headers):
    response = make_request('GET', f"{base_url}/dealGroups", headers=headers)
    if response.status_code == 200:
        return response.json().get("dealGroups", [])
    else:
        print(f"Error retrieving pipelines: {response.status_code}")
        print(response.text)
        return []

def get_activecampaign_stages(base_url, headers, pipeline_id):
    response = make_request('GET', f"{base_url}/dealStages?filters[group]={pipeline_id}", headers=headers)
    if response.status_code == 200:
        return response.json().get("dealStages", [])
    else:
        print(f"Error retrieving stages for pipeline {pipeline_id}: {response.status_code}")
        print(response.text)
        return []

def sync_pipelines_and_stages(base_url, headers):
    pipelines = get_activecampaign_pipelines(base_url, headers)
    
    for pipeline in pipelines:
        with transaction.atomic():
            pipeline_obj, created = PipeLine.objects.update_or_create(
                ac_id=pipeline['id'],
                defaults={
                    'name': pipeline['title'],
                    'ac_json': pipeline
                }
            )
            
            print(f"{'Created' if created else 'Updated'} pipeline: {pipeline_obj.name}")
            
            stages = get_activecampaign_stages(base_url, headers, pipeline['id'])
            for stage in stages:
                stage_obj, stage_created = DealStage.objects.update_or_create(
                    ac_id=stage['id'],
                    defaults={
                        'name': stage['title'],
                        'order': stage['order'],
                        'pipeline': pipeline_obj,
                        'ac_json': stage
                    }
                )
                print(f"{'Created' if stage_created else 'Updated'} stage: {stage_obj.name}")


def get_contact_from_highlevel(contact_id):
    url = f"https://rest.gohighlevel.com/v1/contacts/{contact_id}"
    headers = {
        "Authorization": f"Bearer {os.environ.get('HIGHLEVEL_API_KEY')}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        print(response.json())  # Add this line to print the full response
        return response.json()
    else:
        logger.warning(f"Failed to get contact from HighLevel: {response.status_code} - {response.text}")
        return None


@shared_task(name='sync.run_sync_script')
def run():
    """
    Run the sync process.
    """
    sync_log = SyncLog.objects.create(status='In Progress', start_time=timezone.now())

    try:
        with transaction.atomic():
            logger.setLevel(logging.WARNING)

            # Check HighLevel API connection
            logger.info("Checking HighLevel API connection...")
            if not check_api_connection():
                raise Exception("HighLevel API connection failed.")

            logger.info("HighLevel API connection successful. Proceeding with sync process.")

            base_url = os.environ.get("ACTIVECAMPAIGN_URL")
            if not base_url.startswith("https://"):
                base_url = f"https://{base_url}"
            base_url += ".api-us1.com/api/3"
            
            api_key = os.environ.get("ACTIVECAMPAIGN_KEY")
            
            headers = {
                "Api-Token": api_key,
                "Content-Type": "application/json"
            }

            # Step 1: Sync pipelines and stages
            logger.info("Syncing pipelines and stages...")
            sync_pipelines_and_stages(base_url, headers)
            logger.info("Pipelines and stages sync completed.")

            # Step 2-3: Process contacts, deals, and custom fields
            logger.info("Processing contacts, deals, and custom fields...")
            processed_contacts = get_and_process_activecampaign_contacts()
            
            sync_log.contacts_attempted = processed_contacts
            final_count = Contact.objects.count()
            logger.info(f"\nProcessed and stored {processed_contacts} contacts from ActiveCampaign")
            logger.info(f"Total contacts in database: {final_count}")

            # Schedule individual contact syncs to HighLevel
            logger.info("\nScheduling contact syncs to HighLevel...")
            contacts = Contact.objects.all()
            for contact in contacts:
                sync_contact_to_highlevel_task.delay(contact.id)

            sync_log.contacts_synced = contacts.count()
            sync_log.status = 'Sync Tasks Scheduled'
            sync_log.end_time = timezone.now()
            sync_log.save()

            logger.info("\nContact sync tasks scheduled.")
    except Exception as e:
        sync_log.status = 'Failed'
        sync_log.error_message = str(e)
        sync_log.end_time = timezone.now()
        sync_log.save()
        logger.error(f"Sync process failed: {e}")

    finally:
        if sync_log.status == 'In Progress':
            sync_log.status = 'Interrupted'
            sync_log.end_time = timezone.now()
            sync_log.save()

@shared_task(name='sync.sync_contact_to_highlevel_task')
def sync_contact_to_highlevel_task(contact_id):
    """
    Sync a single contact to HighLevel.
    This function will be called asynchronously by Celery.
    """
    try:
        contact = Contact.objects.get(id=contact_id)
        # Use the imported function from highlevel_sync
        sync_result = sync_contact_to_highlevel(contact)
        logger.info(f"Successfully synced contact {contact_id} to HighLevel")
    except Exception as e:
        logger.error(f"Failed to sync contact {contact_id} to HighLevel: {str(e)}")


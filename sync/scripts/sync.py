import os
import django
from django.db import transaction
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
from ..highlevel_sync import sync_all_contacts_to_highlevel, check_api_connection
from sync.models import SyncLog
from django.utils import timezone

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_project.settings")
django.setup()

from sync.models import Contact, CustomField, ContactCustomField, Deal, DealStage, PipeLine  # Import your Contact model

# Load environment variables and set up request caching
load_dotenv()
requests_cache.install_cache('activecampaign_cache', expire_after=timedelta(hours=24))

# Create a rate-limited session that works with the cache
class CachedLimiterSession(LimiterSession):
    def send(self, request, **kwargs):
        with requests_cache.disabled():
            return super().send(request, **kwargs)

# Create the session with rate limiting
session = CachedLimiterSession(per_second=5)  # Limit to 5 requests per second

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
    contact_obj, created = Contact.objects.update_or_create(
        ac_id=contact['id'],
        defaults={
            'email': contact.get('email'),
            'first_name': contact.get('firstName'),
            'last_name': contact.get('lastName'),
            'ac_json': json.dumps(contact)
        }
    )

    # Process custom fields
    for field in contact.get('custom_fields', []):
        custom_field, _ = CustomField.objects.update_or_create(
            ac_id=field['field'],
            defaults={
                'type': field.get('fieldType', ''),
                'ac_title': field.get('fieldTitle', ''),
                'ac_json': json.dumps(field)
            }
        )

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
        pipeline_id = deal.get('pipeline') or deal.get('group') or deal.get('dealGroup')
        if not pipeline_id:
            print(f"Warning: Deal {deal.get('id')} has no pipeline ID. Attempting to use default pipeline.")
            default_pipeline = PipeLine.objects.first()
            if default_pipeline:
                pipeline_id = default_pipeline.ac_id
            else:
                print(f"Error: No default pipeline found. Skipping deal {deal.get('id')}.")
                continue

        pipeline, _ = PipeLine.objects.get_or_create(
            ac_id=pipeline_id,
            defaults={
                'name': deal.get('pipeline_title') or deal.get('group_title') or 'Unknown Pipeline',
                'ac_json': json.dumps(deal.get('pipeline', {}))
            }
        )

        # Fetch or create the deal stage
        stage_id = deal.get('stage')
        if not stage_id:
            print(f"Warning: Deal {deal.get('id')} has no stage ID. Using default stage.")
            default_stage = DealStage.objects.filter(pipeline=pipeline).first()
            if default_stage:
                stage_id = default_stage.ac_id
            else:
                print(f"Error: No default stage found for pipeline {pipeline.name}. Skipping deal {deal.get('id')}.")
                continue

        stage, _ = DealStage.objects.get_or_create(
            ac_id=stage_id,
            defaults={
                'name': deal.get('stage_title', 'Unknown Stage'),
                'pipeline': pipeline,
                'ac_json': deal.get('stage', {})
            }
        )

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

def get_and_process_activecampaign_contacts(limit=None, test_mode=False):
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
                with transaction.atomic():
                    processed_contact = process_contact(contact) 
                processed_contacts += 1
                pbar.update(1)
                if test_mode:
                    logger.info(f"Processed contact: {processed_contact.first_name} {processed_contact.last_name} (ID: {processed_contact.ac_id})")
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


def run(test_mode=False):
    """
    Run the sync process. If test_mode is True, only process a small batch of contacts
    and provide more detailed logging.
    """
    sync_log = SyncLog.objects.create()

    try:
        if test_mode:
            logger.setLevel(logging.INFO)
            logger.info("Running in test mode with increased verbosity")
        else:
            logger.setLevel(logging.WARNING)

        # Check HighLevel API connection
        logger.info("Checking HighLevel API connection...")
        if not check_api_connection():
            logger.error("HighLevel API connection failed. Aborting sync process.")
            sync_log.status = 'Failed'
            sync_log.error_message = 'HighLevel API connection failed.'
            sync_log.end_time = timezone.now()
            sync_log.save()
            return

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
        processed_contacts = get_and_process_activecampaign_contacts(limit=100 if test_mode else None, test_mode=test_mode)
        
        sync_log.contacts_attempted = processed_contacts
        final_count = Contact.objects.count()
        logger.info(f"\nProcessed and stored {processed_contacts} contacts from ActiveCampaign")
        logger.info(f"Total contacts in database: {final_count}")

        # Sync contacts to HighLevel
        logger.info("\nSyncing contacts to HighLevel...")
        synced_contacts = sync_all_contacts_to_highlevel(limit=100 if test_mode else None, test_mode=test_mode)

        sync_log.contacts_synced = len(synced_contacts)
        sync_log.status = 'Completed'
        sync_log.end_time = timezone.now()
        sync_log.save()

        if test_mode and synced_contacts:
            # Verify contacts in HighLevel
            logger.info("\nVerifying contacts in HighLevel...")
            for contact in synced_contacts:
                if contact.hl_id:
                    highlevel_contact = get_contact_from_highlevel(contact.hl_id)
                    if highlevel_contact:
                        try:
                            logger.info(f"Contact verified in HighLevel: {highlevel_contact['contact']['firstName']} {highlevel_contact['contact']['lastName']} (ID: {contact.hl_id})")
                            
                            # Add links to ActiveCampaign and HighLevel UIs
                            ac_url = f"https://{os.environ.get('ACTIVECAMPAIGN_URL')}.activehosted.com/app/contacts/{contact.ac_id}"
                            hl_url = f"https://app.gohighlevel.com/location/{os.environ.get('HIGHLEVEL_LOCATION_ID')}/contacts/{contact.hl_id}"
                            
                            logger.info(f"ActiveCampaign UI: {ac_url}")
                            logger.info(f"HighLevel UI: {hl_url}")
                        except KeyError:
                            logger.warning(f"Contact found in HighLevel but with unexpected structure: {contact.first_name} {contact.last_name} (ID: {contact.hl_id})")
                            logger.debug(f"HighLevel response: {highlevel_contact}")
                    else:
                        logger.warning(f"Contact not found in HighLevel: {contact.first_name} {contact.last_name} (ID: {contact.hl_id})")
                else:
                    logger.warning(f"Contact has no HighLevel ID: {contact.first_name} {contact.last_name}")

        elif test_mode:
            logger.warning("No contacts were synced to HighLevel.")

        logger.info("\nContact sync completed.")
    except Exception as e:
        sync_log.status = 'Failed'
        sync_log.error_message = str(e)
        sync_log.end_time = timezone.now()
        sync_log.save()
        logger.error(f"Sync process failed: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the ActiveCampaign to HighLevel sync process.")
    parser.add_argument("--test", action="store_true", help="Run in test mode with a small batch of contacts")
    args = parser.parse_args()

    run(test_mode=args.test)


"""
LG ProCentric EPG Bundle Generator

This module orchestrates the fetching and processing of EPG (Electronic Program Guide)
data from multiple sources (Sky NZ and XMLTV) and generates bundles for LG ProCentric servers.
"""
import json
import logging
import os
import traceback
from utils.file_handler import save_and_zip
from utils.webhook_notifier import WebhookNotifier
from epg_sources.xmltv_net.main import XMLTV
from epg_sources.sky_nz.main import SkyNZ_EPG

# Configure logging before any log calls
# Logs are sent to stdout/stderr which Docker automatically captures
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Explicitly use StreamHandler for stdout
    ]
)

# Ensure the 'debug' directory exists
# Use DEBUG_DIR env var if set (for run_local.sh), otherwise use relative path
debug_dir = os.environ.get('DEBUG_DIR', './debug')
if not os.path.exists(debug_dir):
    os.makedirs(debug_dir)  # Create the directory if it doesn't exist

# Initialize webhook notifier
webhook = WebhookNotifier()

# Log webhook configuration at startup
if webhook.enabled:
    logging.info(f"Webhook notifications: ENABLED (Type: {webhook.webhook_type}, URL: {webhook.webhook_url[:50]}...)")
    notify_success = os.environ.get('WEBHOOK_NOTIFY_SUCCESS', 'false').lower() == 'true'
    logging.info(f"Webhook success notifications: {'ENABLED' if notify_success else 'DISABLED'}")
else:
    logging.info("Webhook notifications: DISABLED (WEBHOOK_URL not configured)")

# Track processing errors for summary notification
processing_errors = []

###############################
## For New Zealand
###############################

try:
    epg = SkyNZ_EPG(url="https://api.skyone.co.nz/exp/graph", zip_output_path="./output/EPG/NZ/Procentric_EPG_NZL.zip")
    logging.info("Fetching and parsing the XML data for New Zealand...")
    data = epg.fetch_data()

    if data:
        # Check if the data is valid and write it to a file
        try:
            with open(os.path.join(debug_dir, "debug_skynz.json"), "w") as file:
                # Convert 'data' to a JSON-formatted string and write it to the file
                file.write(json.dumps(data, indent=4))  # Pretty print with an indent for readability
        except (IOError, OSError) as e:
            logging.error(f"Failed to write debug file for Sky NZ: {e}")
        except (TypeError, ValueError) as e:
            logging.error(f"Failed to serialize Sky NZ data to JSON: {e}")

        program_guide = epg.parse_program_data(data)
        if program_guide:
            save_and_zip(program_guide, ["EPG", "NZL"], 'Procentric_EPG_NZL')
        else:
            error_msg = "No program guide data found for New Zealand"
            logging.warning(error_msg)
            processing_errors.append({"location": "New Zealand", "error": error_msg})
    else:
        error_msg = "Failed to fetch data from Sky NZ API"
        logging.error(error_msg)
        processing_errors.append({"location": "New Zealand", "error": error_msg})
        webhook.notify_error(
            error_title="EPG Processing Failed - New Zealand",
            error_message=error_msg
        )
except Exception as e:
    error_msg = f"Unexpected error processing New Zealand EPG: {str(e)}"
    logging.error(error_msg)
    logging.debug(traceback.format_exc())
    processing_errors.append({"location": "New Zealand", "error": error_msg})
    webhook.notify_error(
        error_title="EPG Processing Exception - New Zealand",
        error_message=error_msg,
        exception=e
    )



###############################
## For Australia
###############################
def create_xmltv_source(city: str, url: str, title: str, timezone_offset: int) -> XMLTV:
    return XMLTV(url, title, timezone_offset)

# List of Australian cities to process
cities = [
    # Capital Cities
    {"city": "SYD", "url": "http://xmltv.net/xml_files/Sydney.xml", "title": "Pro:Centric JSON Program Guide Data AUS Sydney", "timezone": 11},  # AEDT
    {"city": "MEL", "url": "http://xmltv.net/xml_files/Melbourne.xml", "title": "Pro:Centric JSON Program Guide Data AUS Melbourne", "timezone": 11},  # AEDT
    {"city": "BNE", "url": "http://xmltv.net/xml_files/Brisbane.xml", "title": "Pro:Centric JSON Program Guide Data AUS Brisbane", "timezone": 10},  # AEST
    {"city": "PER", "url": "http://xmltv.net/xml_files/Perth.xml", "title": "Pro:Centric JSON Program Guide Data AUS Perth", "timezone": 8},  # AWST
    {"city": "ADL", "url": "http://xmltv.net/xml_files/Adelaide.xml", "title": "Pro:Centric JSON Program Guide Data AUS Adelaide", "timezone": 10.5},  # ACDT
    {"city": "CBR", "url": "http://xmltv.net/xml_files/Canberra.xml", "title": "Pro:Centric JSON Program Guide Data AUS Canberra", "timezone": 11},  # AEDT
    {"city": "HBA", "url": "http://xmltv.net/xml_files/Hobart.xml", "title": "Pro:Centric JSON Program Guide Data AUS Hobart", "timezone": 11},  # AEDT
    {"city": "DRW", "url": "http://xmltv.net/xml_files/Darwin.xml", "title": "Pro:Centric JSON Program Guide Data AUS Darwin", "timezone": 9.5},  # ACST

    # Major Regional Cities
    {"city": "ALB", "url": "http://xmltv.net/xml_files/Albany.xml", "title": "Pro:Centric JSON Program Guide Data AUS Albany", "timezone": 8},  # AWST
    {"city": "ABX", "url": "http://xmltv.net/xml_files/Albury_Wodonga.xml", "title": "Pro:Centric JSON Program Guide Data AUS Albury/Wodonga", "timezone": 11},  # AEDT
    {"city": "BNK", "url": "http://xmltv.net/xml_files/Ballarat.xml", "title": "Pro:Centric JSON Program Guide Data AUS Ballarat", "timezone": 11},  # AEDT
    {"city": "BDO", "url": "http://xmltv.net/xml_files/Bendigo.xml", "title": "Pro:Centric JSON Program Guide Data AUS Bendigo", "timezone": 11},  # AEDT
    {"city": "BHI", "url": "http://xmltv.net/xml_files/Broken_Hill.xml", "title": "Pro:Centric JSON Program Guide Data AUS Broken Hill", "timezone": 10.5},  # ACDT
    {"city": "BUY", "url": "http://xmltv.net/xml_files/Bunbury.xml", "title": "Pro:Centric JSON Program Guide Data AUS Bunbury", "timezone": 8},  # AWST
    {"city": "CNS", "url": "http://xmltv.net/xml_files/Cairns.xml", "title": "Pro:Centric JSON Program Guide Data AUS Cairns", "timezone": 10},  # AEST
    {"city": "CCN", "url": "http://xmltv.net/xml_files/Central_Coast.xml", "title": "Pro:Centric JSON Program Guide Data AUS Central Coast NSW", "timezone": 11},  # AEDT
    {"city": "CFS", "url": "http://xmltv.net/xml_files/Coffs_Harbour.xml", "title": "Pro:Centric JSON Program Guide Data AUS Coffs Harbour", "timezone": 11},  # AEDT
    {"city": "GEX", "url": "http://xmltv.net/xml_files/Geelong.xml", "title": "Pro:Centric JSON Program Guide Data AUS Geelong", "timezone": 11},  # AEDT
    {"city": "GPL", "url": "http://xmltv.net/xml_files/Gippsland.xml", "title": "Pro:Centric JSON Program Guide Data AUS Gippsland", "timezone": 11},  # AEDT
    {"city": "OOL", "url": "http://xmltv.net/xml_files/Goldcoast.xml", "title": "Pro:Centric JSON Program Guide Data AUS Gold Coast", "timezone": 10},  # AEST
    {"city": "GFN", "url": "http://xmltv.net/xml_files/Griffith.xml", "title": "Pro:Centric JSON Program Guide Data AUS Griffith", "timezone": 11},  # AEDT
    {"city": "JUR", "url": "http://xmltv.net/xml_files/Jurien_Bay.xml", "title": "Pro:Centric JSON Program Guide Data AUS Jurien Bay", "timezone": 8},  # AWST
    {"city": "LST", "url": "http://xmltv.net/xml_files/Launceston.xml", "title": "Pro:Centric JSON Program Guide Data AUS Launceston", "timezone": 11},  # AEDT
    {"city": "LSM", "url": "http://xmltv.net/xml_files/Lismore.xml", "title": "Pro:Centric JSON Program Guide Data AUS Lismore", "timezone": 11},  # AEDT
    {"city": "MKY", "url": "http://xmltv.net/xml_files/Mackay.xml", "title": "Pro:Centric JSON Program Guide Data AUS Mackay", "timezone": 10},  # AEST
    {"city": "MAN", "url": "http://xmltv.net/xml_files/Mandurah.xml", "title": "Pro:Centric JSON Program Guide Data AUS Mandurah", "timezone": 8},  # AWST
    {"city": "MQL", "url": "http://xmltv.net/xml_files/Mildura_Sunraysia.xml", "title": "Pro:Centric JSON Program Guide Data AUS Mildura/Sunraysia", "timezone": 10.5},  # ACDT
    {"city": "NTL", "url": "http://xmltv.net/xml_files/Newcastle.xml", "title": "Pro:Centric JSON Program Guide Data AUS Newcastle", "timezone": 11},  # AEDT
    {"city": "OAG", "url": "http://xmltv.net/xml_files/Orange_Dubbo.xml", "title": "Pro:Centric JSON Program Guide Data AUS Orange/Dubbo", "timezone": 11},  # AEDT
    {"city": "PUG", "url": "http://xmltv.net/xml_files/Port_Augusta.xml", "title": "Pro:Centric JSON Program Guide Data AUS Port Augusta", "timezone": 10.5},  # ACDT
    {"city": "RMK", "url": "http://xmltv.net/xml_files/Renmark.xml", "title": "Pro:Centric JSON Program Guide Data AUS Renmark", "timezone": 10.5},  # ACDT
    {"city": "RVL", "url": "http://xmltv.net/xml_files/Riverland.xml", "title": "Pro:Centric JSON Program Guide Data AUS Riverland", "timezone": 10.5},  # ACDT
    {"city": "ROK", "url": "http://xmltv.net/xml_files/Rockhampton.xml", "title": "Pro:Centric JSON Program Guide Data AUS Rockhampton", "timezone": 10},  # AEST
    {"city": "SHE", "url": "http://xmltv.net/xml_files/Shepparton.xml", "title": "Pro:Centric JSON Program Guide Data AUS Shepparton", "timezone": 11},  # AEDT
    {"city": "SCN", "url": "http://xmltv.net/xml_files/South_Coast.xml", "title": "Pro:Centric JSON Program Guide Data AUS South Coast NSW", "timezone": 11},  # AEDT
    {"city": "SES", "url": "http://xmltv.net/xml_files/South_East_SA.xml", "title": "Pro:Centric JSON Program Guide Data AUS South East SA", "timezone": 10.5},  # ACDT
    {"city": "SPG", "url": "http://xmltv.net/xml_files/Spencer_Gulf.xml", "title": "Pro:Centric JSON Program Guide Data AUS Spencer Gulf", "timezone": 10.5},  # ACDT
    {"city": "MCY", "url": "http://xmltv.net/xml_files/Sunshine_Coast.xml", "title": "Pro:Centric JSON Program Guide Data AUS Sunshine Coast", "timezone": 10},  # AEST
    {"city": "TMW", "url": "http://xmltv.net/xml_files/Tamworth.xml", "title": "Pro:Centric JSON Program Guide Data AUS Tamworth", "timezone": 11},  # AEDT
    {"city": "TPM", "url": "http://xmltv.net/xml_files/Taree_Port_Macquarie.xml", "title": "Pro:Centric JSON Program Guide Data AUS Taree/Port Macquarie", "timezone": 11},  # AEDT
    {"city": "TWB", "url": "http://xmltv.net/xml_files/Toowoomba.xml", "title": "Pro:Centric JSON Program Guide Data AUS Toowoomba", "timezone": 10},  # AEST
    {"city": "TSV", "url": "http://xmltv.net/xml_files/Townsville.xml", "title": "Pro:Centric JSON Program Guide Data AUS Townsville", "timezone": 10},  # AEST
    {"city": "WGA", "url": "http://xmltv.net/xml_files/Wagga_Wagga.xml", "title": "Pro:Centric JSON Program Guide Data AUS Wagga Wagga", "timezone": 11},  # AEDT
    {"city": "WBY", "url": "http://xmltv.net/xml_files/Wide_Bay.xml", "title": "Pro:Centric JSON Program Guide Data AUS Wide Bay", "timezone": 10},  # AEST
    {"city": "WOL", "url": "http://xmltv.net/xml_files/Wollongong.xml", "title": "Pro:Centric JSON Program Guide Data AUS Wollongong", "timezone": 11},  # AEDT

    # Regional Bundles
    {"city": "NSWREG", "url": "http://xmltv.net/xml_files/Remote_Central.xml", "title": "Pro:Centric JSON Program Guide Data AUS NSW Regional", "timezone": 11},  # AEDT
    {"city": "NTREG", "url": "http://xmltv.net/xml_files/NT_Regional.xml", "title": "Pro:Centric JSON Program Guide Data AUS NT Regional", "timezone": 9.5},  # ACST
    {"city": "QLDREG", "url": "http://xmltv.net/xml_files/QLD_Regional.xml", "title": "Pro:Centric JSON Program Guide Data AUS QLD Regional", "timezone": 10},  # AEST
    {"city": "SAREG", "url": "http://xmltv.net/xml_files/SA_Regional.xml", "title": "Pro:Centric JSON Program Guide Data AUS SA Regional", "timezone": 10.5},  # ACDT
    {"city": "TASREG", "url": "http://xmltv.net/xml_files/TAS_Regional.xml", "title": "Pro:Centric JSON Program Guide Data AUS TAS Regional", "timezone": 11},  # AEDT
    {"city": "WAREG", "url": "http://xmltv.net/xml_files/WA_Regional.xml", "title": "Pro:Centric JSON Program Guide Data AUS WA Regional", "timezone": 8}  # AWST
]

def XMLTVProcess(source: XMLTV, location_tags: list, file_prefix: str, city_code: str):
    try:
        logging.info(f"Fetching and parsing the XML data for '{source.title}'...")
        program_guide = source.get_program_guide()

        if program_guide:
            logging.info(f"Successfully fetched and parsed the XML data for '{source.title}'.")

            save_and_zip(program_guide, location_tags, file_prefix)
            logging.info(f"Data for '{source.title}' has been saved and zipped successfully.")
        else:
            error_msg = f"No program guide data found for '{source.title}'"
            logging.warning(error_msg)
            processing_errors.append({"location": f"Australia - {city_code}", "error": error_msg})

    except Exception as e:
        error_msg = f"Error occurred while processing '{source.title}': {str(e)}"
        logging.error(error_msg)
        logging.debug(traceback.format_exc())
        processing_errors.append({"location": f"Australia - {city_code}", "error": error_msg})
        webhook.notify_error(
            error_title=f"EPG Processing Failed - {city_code}",
            error_message=error_msg,
            exception=e
        )

# Process Australian cities
for city in cities:
    timezone_offset = city.get("timezone", 0)  # Use the configured timezone
    source = create_xmltv_source(city["city"], city["url"], city["title"], timezone_offset)
    XMLTVProcess(source, ["EPG", "AUS", city["city"]], f"Procentric_EPG_{city['city']}", city["city"])

# Send summary notification if there were any errors
if processing_errors:
    error_summary = f"EPG processing completed with {len(processing_errors)} error(s):\n"
    for err in processing_errors[:5]:  # Limit to first 5 errors in summary
        error_summary += f"\n• {err['location']}: {err['error']}"

    if len(processing_errors) > 5:
        error_summary += f"\n\n... and {len(processing_errors) - 5} more errors"

    webhook.notify_warning(
        warning_title=f"EPG Processing Summary - {len(processing_errors)} Error(s)",
        warning_message=error_summary
    )
    logging.warning(f"EPG processing completed with {len(processing_errors)} error(s)")
else:
    logging.info("EPG processing completed successfully with no errors")
    # Optionally send success notification
    if os.environ.get('WEBHOOK_NOTIFY_SUCCESS', 'false').lower() == 'true':
        webhook.notify_success(
            title="EPG Processing Successful",
            message=f"All EPG bundles generated successfully for New Zealand and {len(cities)} Australian cities"
        )

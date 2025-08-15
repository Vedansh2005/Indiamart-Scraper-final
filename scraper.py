import argparse
import os
import time
import csv
import random
import logging
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from fake_useragent import UserAgent
from fuzzywuzzy import fuzz # For calculating relevancy score

# --- UTILITY FUNCTIONS ---

def setup_logger():
    """Set up and configure the logger."""
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"scraper_{timestamp}.log")

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger()

def retry(max_attempts=3, delay=2):
    """Decorator to retry a function if it fails due to transient errors."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logging.warning(f"Attempt {attempts}/{max_attempts} failed for '{func._name_}' with error: {e}. Retrying in {delay} seconds...")
                    time.sleep(delay)
                    if attempts == max_attempts:
                        logging.error(f"Function '{func._name_}' failed after {max_attempts} attempts.")
                        raise # Re-raise the last exception if all attempts fail
        return wrapper
    return decorator

def sanitize_data(data):
    """Clean and sanitize data for CSV export."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = value.strip()
                data[key] = data[key].replace('\n', ' ').replace('\t', ' ')
                while '  ' in data[key]:
                    data[key] = data[key].replace('  ', ' ')
    return data

def validate_phone(phone):
    """Validate and format phone numbers (specifically for Indian numbers)."""
    if not phone:
        return ""
    digits = ''.join(filter(str.isdigit, phone))
    if len(digits) == 10:
        return digits
    elif len(digits) in [11, 12] and digits.startswith(('91', '0')):
        return digits[-10:]
    return phone # Return original if not a clear 10-digit or Indian format

def validate_email(email):
    """Validate email addresses."""
    if not email:
        return ""
    # Basic validation: check for '@' and '.' after '@'
    if '@' in email and '.' in email.split('@')[1]:
        return email.strip().lower()
    return ""

# --- INDIA MART SCRAPER CLASS ---

class IndiaMartScraper:
    def __init__(self, headless=False, mobile_number=None):
        """
        Initializes the IndiaMartScraper with headless mode option.
        :param headless: If True, run Chrome in headless mode (no UI).
        :param mobile_number: Mobile number for IndiaMART login (default: prompts user input)
        """
        self.base_url = "https://www.indiamart.com/" # Base URL is still useful for general reference
        self.driver = None
        self.leads = []
        self.logger = setup_logger()
        self.headless = headless
        self.mobile_number = mobile_number
        self._setup_driver() # Internal method for driver setup

    def _setup_driver(self):
        """Sets up the Selenium WebDriver with appropriate options."""
        self.logger.info("Setting up the browser...")
        try:
            ua = UserAgent()
            user_agent = ua.random

            chrome_options = Options()
            if self.headless:
                self.logger.info("Running in headless mode")
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--window-size=1920,1080")

            # Essential arguments for robust scraping
            chrome_options.add_argument(f"user-agent={user_agent}")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-gpu")
            
            # Dynamically assign a random port for remote debugging
            random_port = random.randint(9000, 10000)
            chrome_options.add_argument(f"--remote-debugging-port={random_port}") 
            self.logger.info(f"Using remote debugging port: {random_port}")

            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30) # Set a page load timeout
            self.logger.info("Browser setup complete")
        except Exception as e:
            self.logger.error(f"Failed to set up browser: {e}")
            print("\nERROR: Could not initialize the browser. Please check your Chrome installation.")
            print("Possible solutions:")
            print("1. Make sure Chrome is installed and up to date")
            print("2. Try running the script with administrator privileges")
            print("3. Check if your antivirus is blocking Chrome automation")
            raise # Re-raise to stop execution if driver fails to set up

    @retry(max_attempts=3, delay=2)
    def login(self):
        """Navigates to IndiaMART buyer page and handles OTP-based login."""
        self.logger.info("Navigating to IndiaMART buyer login page...")
        try:
            # Navigate directly to the buyer login page
            self.driver.get("https://buyer.indiamart.com/")
            # Wait for the URL to contain the buyer domain, indicating page load
            WebDriverWait(self.driver, 15).until(EC.url_contains("buyer.indiamart.com"))
            self.logger.info(f"Navigated to buyer login page. Current URL: {self.driver.current_url}")
            time.sleep(3) # Time break: once the page loads

            # Get mobile number from instance or prompt user
            if self.mobile_number:
                mobile_number = validate_phone(self.mobile_number)
            else:
                mobile_number = input("Enter your IndiaMART registered mobile number: ")
                mobile_number = validate_phone(mobile_number)
            
            if not mobile_number or len(mobile_number) != 10:
                self.logger.error(f"Invalid mobile number: {mobile_number}. Please enter a valid 10-digit number.")
                print(f"Invalid mobile number: {mobile_number}. Please enter a valid 10-digit number.")
                return False

            # Find and fill mobile input field
            # Using id="mobilemy" from provided HTML
            mobile_input = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "mobilemy")) 
            )
            mobile_input.send_keys(mobile_number)
            self.logger.info(f"Entered mobile number: {mobile_number}")
            time.sleep(3) # Time break: after phone number is entered, before submitting

            # Find and click "Send OTP" button
            # Using id="signInSubmitButton" and value="Send OTP" from provided HTML
            send_otp_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@id='signInSubmitButton' and @value='Send OTP']"))
            )
            send_otp_button.click()
            self.logger.info("Clicked 'Send OTP' button.")
            time.sleep(3) # Give time for OTP input field to appear

            # Prompt for OTP
            otp = input("Enter the OTP received: ")

            # Find and fill OTP input field
            # Using type, placeholder, and maxlength from provided HTML as it has no ID
            otp_input = WebDriverWait(self.driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, "//input[@type='text' and @placeholder='----' and @maxlength='4']"))
            )
            otp_input.send_keys(otp)
            self.logger.info("Entered OTP.")

            # Find and click "Verify OTP" button
            # Using id="signInSubmitButton" and value="Verify OTP" from provided HTML
            verify_otp_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@id='signInSubmitButton' and @value='Verify OTP']"))
            )
            verify_otp_button.click()
            self.logger.info("Clicked 'Verify OTP' button.")

            # Wait for successful login indicators on the buyer page (e.g., URL change, presence of dashboard elements)
            WebDriverWait(self.driver, 15).until(
                EC.any_of(
                    EC.url_contains("buyer.indiamart.com/"), # URL changes from the login form to dashboard
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'My Account') or contains(text(), 'Dashboard') or contains(text(), 'My Orders') or contains(text(), 'Post Your Requirement')]"))
                )
            )
            self.logger.info("Login process successful!")
            return True

        except TimeoutException:
            self.logger.error("Login process timed out. Elements not found or page did not load.")
            self.driver.save_screenshot("login_timeout_error.png")
            return False
        except NoSuchElementException:
            self.logger.error("Login elements not found on the page.")
            self.driver.save_screenshot("login_elements_missing.png")
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during login: {e}")
            self.driver.save_screenshot("login_unexpected_error.png")
            return False

    @retry(max_attempts=3, delay=2)
    def search_product(self, keyword):
        """
        Searches for a product using the given keyword.
        :param keyword: The product keyword to search for.
        :return: True if search initiated successfully, False otherwise.
        """
        self.logger.info(f"Initiating search for: {keyword}")
        # Store original window handle before potential new tab opens
        main_window_handle = self.driver.current_window_handle 
        try:
            # 1. Wait for the input box to be load then try to input the keyword
            time.sleep(3) # Wait for 3 seconds after login for the page to fully settle.
            search_input_box = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.ID, "search_string")) # Targeting id="search_string"
            )
            search_input_box.clear()
            search_input_box.send_keys(keyword)
            self.logger.info(f"Entered keyword '{keyword}' into the search input box (id='search_string').")
            
            # 2. Click the first search button (magnifying glass icon/text "Search")
            first_search_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".rvmp_srch_button")) # Targeting class "rvmp_srch_button"
            )
            first_search_button.click()
            self.logger.info("Clicked the first search button (rvmp_srch_button).")
            
            time.sleep(2) # Wait for 2 seconds after clicking the first search button

            # 3. Click the second search button (class="adv-btn search-button")
            # This click opens a new tab, so we need to prepare to switch.
            second_search_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".adv-btn.search-button")) # Targeting classes "adv-btn" and "search-button"
            )
            second_search_button.click()
            self.logger.info("Clicked the second search button (adv-btn search-button).")
            
            # --- New tab handling logic ---
            # Wait for a new window/tab to open (expecting 2 windows now)
            WebDriverWait(self.driver, 20).until(EC.number_of_windows_to_be(2))
            
            # Switch to the new window/tab (the one that is not the original main_window_handle)
            new_window_handle = [window_handle for window_handle in self.driver.window_handles if window_handle != main_window_handle][0]
            self.driver.switch_to.window(new_window_handle)
            self.logger.info(f"Switched to new window/tab: {self.driver.current_url}")
            # --- End of New tab handling logic ---

            # Wait for the main container of listing cards to be present on the new tab
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "listingCardContainer"))
            )
            self.logger.info("Search results page loaded (listingCardContainer found).")

            # --- START: New logic for "All India" city selection ---
            self.logger.info("Attempting to set city to 'All India'.")
            time.sleep(3) # Added 3-second delay before setting All India filter
            try:
                # Click the city dropdown button
                city_dropdown_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "hd_searchPlace"))
                )
                city_dropdown_button.click()
                self.logger.info("Clicked city dropdown button.")
                time.sleep(2) # Allow city suggestion list to appear

                # Find and click the "All India" option
                all_india_option = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'imas-item') and contains(@class, 'imas-city-text') and @data-value='All India']"))
                )
                all_india_option.click()
                self.logger.info("Selected 'All India' city option.")
                time.sleep(5) # Give time for the page to reload/update with new city results
                
                # Wait for listingCardContainer to be present again after city change
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "listingCardContainer"))
                )
                self.logger.info("Listing cards re-loaded after 'All India' selection.")

            except TimeoutException:
                self.logger.warning("City dropdown or 'All India' option not found/interactable. Proceeding without city filter.")
            except NoSuchElementException:
                self.logger.warning("City dropdown or 'All India' option not found. Proceeding without city filter.")
            except Exception as e:
                self.logger.error(f"Error while trying to set city to 'All India': {e}")
            # --- END: New logic for "All India" city selection ---

            # --- START: New logic for "Show more results" button ---
            self.logger.info("Attempting to click 'Show more results' button repeatedly.")
            while True:
                try:
                    show_more_button = WebDriverWait(self.driver, 5).until( # Short wait for button visibility
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".showmoreresultsdiv button"))
                    )
                    show_more_button.click()
                    self.logger.info("Clicked 'Show more results' button.")
                    time.sleep(random.uniform(2, 4)) # Wait for new results to load
                except (TimeoutException, NoSuchElementException):
                    self.logger.info("'Show more results' button no longer visible or timed out.")
                    break # Exit loop if button is not found or not clickable
                except Exception as e:
                    self.logger.error(f"Error clicking 'Show more results': {e}")
                    break # Exit loop on unexpected error
            self.logger.info("Finished clicking 'Show more results' buttons.")
            # --- END: New logic for "Show more results" button ---

            return True
        except TimeoutException:
            self.logger.error("Search page or elements timed out.")
            self.driver.save_screenshot("search_timeout_error.png")
            # Ensure we close the new tab if it opened and error occurred before returning to main
            if len(self.driver.window_handles) > 1 and self.driver.current_window_handle != main_window_handle:
                try:
                    self.driver.close()
                except WebDriverException as e:
                    self.logger.warning(f"Could not close new window on timeout: {e}")
            self.driver.switch_to.window(main_window_handle) # Always return to main window on error
            return False
        except Exception as e:
            self.logger.error(f"Error during search for '{keyword}': {e}")
            self.driver.save_screenshot("search_error.png")
            # Ensure we close the new tab if it opened and error occurred before returning to main
            if len(self.driver.window_handles) > 1 and self.driver.current_window_handle != main_window_handle:
                try:
                    self.driver.close()
                except WebDriverException as e:
                    self.logger.warning(f"Could not close new window on error: {e}")
            self.driver.switch_to.window(main_window_handle) # Always return to main window on error
            return False
        # The driver will remain on the new tab if search is successful.
        # Cleanup of all tabs will be handled by the run() method's finally block via self.close().


    def _extract_seller_info_from_listing(self, seller_element):
        """
        Extracts basic information from a seller listing element on the search results page.
        This method is designed to extract data that is directly visible on the card.
        For phone/email/detailed address, _extract_detailed_info_from_profile will be called if needed.
        :param seller_element: The WebDriver element representing a single seller listing.
        :return: A dictionary of extracted seller information.
        """
        seller_info = {
            "Company Name": "",
            "Company Profile URL": "",
            "Product Title/Description": "",
            "Product Catalog URL": "", # New field for catalog link
            "Price": "Not Listed",
            "Address": "",
            "Phone Number": "",
            "Email": "",
            "Relevancy Score (%)": 0 # This will be calculated later
        }

        try:
            # Extract Product Name and Product URL
            try:
                product_name_element = seller_element.find_element(By.CSS_SELECTOR, ".producttitle .cardlinks")
                seller_info["Product Title/Description"] = product_name_element.text.strip()
                seller_info["Company Profile URL"] = product_name_element.get_attribute("href") # This is often the product/company page
            except NoSuchElementException:
                self.logger.debug("Product title/description or its link not found.")

            # Extract Price
            try:
                price_element = seller_element.find_element(By.CSS_SELECTOR, "p.price")
                seller_info["Price"] = price_element.text.strip()
            except NoSuchElementException:
                self.logger.debug("Price not found.")

            # Extract Company Name
            try:
                company_name_element = seller_element.find_element(By.CSS_SELECTOR, ".companyname .cardlinks")
                seller_info["Company Name"] = company_name_element.text.strip()
                # If Company Profile URL wasn't set by product link, try to get it from company name link
                if not seller_info["Company Profile URL"]:
                    seller_info["Company Profile URL"] = company_name_element.get_attribute("href")
            except NoSuchElementException:
                self.logger.debug("Company name or its link not found.")

            # Extract Location (short version from highlight span, then try full address)
            try:
                short_location_element = seller_element.find_element(By.CSS_SELECTOR, ".newLocationUi .highlight")
                seller_info["Address"] = short_location_element.text.strip()
            except NoSuchElementException:
                self.logger.debug("Short location not found.")
            
            try: # Try to get full address if available, overwriting short one
                full_address_element = seller_element.find_element(By.CSS_SELECTOR, "#citytt1 p")
                if full_address_element.text.strip():
                    seller_info["Address"] = full_address_element.text.strip()
            except NoSuchElementException:
                self.logger.debug("Full address (citytt1 p) not found.")
            
            # Direct Phone Number extraction from card (if visible without click)
            try:
                direct_phone_element = seller_element.find_element(By.CSS_SELECTOR, ".contactnumber .pns_h")
                if direct_phone_element.is_displayed():
                    seller_info["Phone Number"] = validate_phone(direct_phone_element.text.strip())
                    self.logger.debug(f"Direct phone number found on card: {seller_info['Phone Number']}")
            except NoSuchElementException:
                self.logger.debug("Direct phone number element not found on card initially.")

            # Email cannot be reliably extracted from card without clicking, so it will be empty here initially.
            # Product Catalog URL is also unlikely to be on the card.
            # These will be handled by _extract_detailed_info_from_profile if needed.

        except Exception as e:
            self.logger.warning(f"Error extracting basic seller info from listing: {e}")
        return seller_info

    @retry(max_attempts=2, delay=1)
    def _extract_detailed_info_from_profile(self, seller_info, search_results_window_handle):
        """
        Visits the company's profile page to extract more detailed information:
        Phone Number (by clicking "View Mobile Number"), Email, and Product Catalog URL.
        :param seller_info: The dictionary containing existing seller information (must have 'Company Profile URL').
        :param search_results_window_handle: The handle of the search results window to return to.
        """
        # Only visit profile if we still need phone, email, or catalog, and a profile URL exists
        if (not seller_info.get("Phone Number") or not seller_info.get("Email") or not seller_info.get("Product Catalog URL")) and seller_info.get("Company Profile URL"):
            self.logger.info(f"Visiting profile for detailed info: {seller_info['Company Profile URL']}")
            new_window_handle = None # Initialize to None

            try:
                # Store handles before opening new window to easily find the new one
                old_handles = self.driver.window_handles
                self.driver.execute_script(f"window.open('{seller_info['Company Profile URL']}', '_blank');")
                
                # Wait for a new window to appear
                WebDriverWait(self.driver, 10).until(EC.new_window_is_opened(old_handles))
                
                # Find the new window handle
                for handle in self.driver.window_handles:
                    if handle not in old_handles: # The new handle is the one not in the old set
                        new_window_handle = handle
                        break
                
                if new_window_handle: # Ensure new_window_handle was found before switching
                    self.driver.switch_to.window(new_window_handle) # Switch to the new tab
                    WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    time.sleep(random.uniform(2, 4)) # Allow content to load

                    # --- Extract Product Title/Description (if not already set from listing) ---
                    if not seller_info["Product Title/Description"]:
                        try:
                            product_title_element = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "#firstheading h1"))
                            )
                            seller_info["Product Title/Description"] = product_title_element.text.strip()
                            self.logger.debug(f"Extracted product title from profile: {seller_info['Product Title/Description']}")
                        except (NoSuchElementException, TimeoutException):
                            self.logger.debug("Product title not found on profile page.")

                    # --- Extract Price (if not already set from listing) ---
                    if seller_info["Price"] == "Not Listed":
                        try:
                            price_element = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "#askprice_pg-1"))
                            )
                            seller_info["Price"] = price_element.text.strip()
                            self.logger.debug(f"Extracted price from profile: {seller_info['Price']}")
                        except (NoSuchElementException, TimeoutException):
                            self.logger.debug("Price not found on profile page.")

                    # --- Extract Company Name (if not already set from listing) ---
                    if not seller_info["Company Name"]:
                        try:
                            company_name_element = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, ".company_details h2"))
                            )
                            seller_info["Company Name"] = company_name_element.text.strip()
                            self.logger.debug(f"Extracted company name from profile: {seller_info['Company Name']}")
                        except (NoSuchElementException, TimeoutException):
                            self.logger.debug("Company name not found on profile page.")

                    # --- Extract Location/Address (more detailed from profile) ---
                    # Overwrite if more detailed address is found
                    try:
                        # Look for the specific location span within the product details section
                        location_span = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'center-heading')]/following-sibling::div[contains(@style, 'margin-top:5px')]//span[contains(@class, 'city-highlight')]/parent::div"))
                        )
                        seller_info["Address"] = location_span.text.strip()
                        self.logger.info(f"Extracted detailed address from product details: {seller_info['Address']}")
                    except (NoSuchElementException, TimeoutException):
                        self.logger.debug("Detailed location from product heading not found. Trying seller contact details section.")
                        try:
                            # Fallback to address in seller contact details section
                            seller_address_element = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "#directions span.color1.dcell.verT.fs13"))
                            )
                            seller_info["Address"] = seller_address_element.text.strip()
                            self.logger.info(f"Extracted detailed address from seller contact: {seller_info['Address']}")
                        except (NoSuchElementException, TimeoutException):
                            self.logger.debug("Detailed address from seller contact not found.")
                    
                    # --- Extract Phone Number (by clicking "View Mobile No." if needed) ---
                    if not seller_info["Phone Number"]:
                        try:
                            # The "View Mobile No." button is a div with specific ID
                            view_mobile_button = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.ID, "mn_mask_pg-1")) # Targeting the div by its ID
                            )
                            view_mobile_button.click()
                            self.logger.debug("Clicked 'View Mobile No.' button on profile page.")
                            time.sleep(1.5) # Small pause for the number to appear

                            # The revealed number is now in a span with class 'bo duet ml5' inside a div with class 'vn_cl View_Mobile_Number'
                            revealed_phone_element = WebDriverWait(self.driver, 5).until(
                                EC.visibility_of_element_located((By.CSS_SELECTOR, ".vn_cl.View_Mobile_Number.w90 span.bo.duet.ml5"))
                            )
                            seller_info["Phone Number"] = validate_phone(revealed_phone_element.text.strip())
                            self.logger.info(f"Extracted phone from profile (after click): {seller_info['Phone Number']}")
                        except (NoSuchElementException, TimeoutException):
                            self.logger.debug("Phone number or view button not found/interactable on profile page.")
                        except Exception as e:
                            self.logger.warning(f"Error extracting phone from profile (after click): {e}")
                    
                    # --- Extract Email ---
                    if not seller_info["Email"]:
                        try:
                            # Look for the "Send Email" button and check for mailto link or text
                            email_element = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.ID, "email_pg-1")) # This is the div for "Send Email"
                            )
                            # Check if there's a mailto link within this div or its children
                            mailto_link_element = email_element.find_elements(By.XPATH, ".//a[contains(@href, 'mailto:')]")
                            if mailto_link_element:
                                mailto_href = mailto_link_element[0].get_attribute("href")
                                seller_info["Email"] = validate_email(mailto_href.replace("mailto:", "").strip())
                            else:
                                # Sometimes the email might be directly visible as text near the button
                                # This is a heuristic, might need specific selector if available
                                email_text_candidates = self.driver.find_elements(By.XPATH, "//*[contains(text(), '@') and contains(text(), '.com')]")
                                for candidate in email_text_candidates:
                                    extracted_email = validate_email(candidate.text.strip())
                                    if extracted_email:
                                        seller_info["Email"] = extracted_email
                                        break
                            self.logger.info(f"Extracted email from profile: {seller_info['Email']}")
                        except (NoSuchElementException, TimeoutException):
                            self.logger.debug("Email element not found on profile page.")
                        except Exception as e:
                            self.logger.warning(f"Error extracting email from profile: {e}")

                    # --- Extract Product Catalog URL ---
                    if not seller_info["Product Catalog URL"]:
                        try:
                            # Common selectors for catalog/brochure/download links
                            catalog_links = self.driver.find_elements(By.XPATH,
                                "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'catalog') and contains(@href, '.pdf')]"
                                " | //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'brochure') and contains(@href, '.pdf')]"
                                " | //a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'download') and contains(@href, '.pdf')]"
                                " | //a[contains(@href, 'catalog.indiamart.com') or contains(@href, 'brochure.indiamart.com')]" # Specific Indiamart catalog domains
                                " | //a[contains(@class, 'catalog-link') or contains(@class, 'download-brochure')]"
                            )
                            for link in catalog_links:
                                href = link.get_attribute('href')
                                if href and ('.pdf' in href.lower() or 'catalog.indiamart.com' in href or 'brochure.indiamart.com' in href):
                                    seller_info["Product Catalog URL"] = href
                                    self.logger.info(f"Extracted Product Catalog URL: {seller_info['Product Catalog URL']}")
                                    break
                        except Exception as e:
                            self.logger.debug(f"Could not extract Product Catalog URL from profile: {e}")

                else: # new_window_handle was not found
                    self.logger.error(f"Failed to switch to new window for profile: {seller_info['Company Profile URL']}")
                    raise NoSuchElementException("New window handle not found after opening profile URL.") # Changed to NoSuchElementException for clarity

            except WebDriverException as e:
                self.logger.error(f"WebDriver error during detailed info extraction for {seller_info.get('Company Profile URL')}: {e}")
                self.driver.save_screenshot("profile_page_error.png")
                raise # Re-raise to trigger retry
            except Exception as e:
                self.logger.error(f"An unexpected error during detailed info extraction for {seller_info.get('Company Profile URL')}: {e}")
                self.driver.save_screenshot("profile_page_unexpected_error.png")
                raise # Re-raise to trigger retry
            finally:
                # Ensure we close the new tab and switch back to the main window
                # Check if new_window_handle was successfully obtained and is still in driver.window_handles
                if new_window_handle and new_window_handle in self.driver.window_handles:
                    try:
                        self.driver.switch_to.window(new_window_handle) # Ensure focus is on it before closing
                        self.driver.close()
                        self.logger.info("Closed profile tab.")
                    except WebDriverException as e:
                        self.logger.warning(f"Could not close window {new_window_handle}: {e}")
                
                # Always switch back to the search results window, even if it was already the active one
                try:
                    self.driver.switch_to.window(search_results_window_handle) # Use the passed handle
                    self.logger.info("Switched back to search results window.")
                except WebDriverException as e:
                    self.logger.error(f"Could not switch back to search results window {search_results_window_handle}: {e}")
                    # If search results window is also gone, the driver might be in a bad state.
                    # This might require re-initializing the driver or stopping.
                    # For now, just log and let the main run() block handle the final close.
        else:
            self.logger.debug("Skipping detailed profile extraction (no URL or all required info already found).")


    def _calculate_relevancy_score(self, seller_info, keyword):
        """
        Calculates a relevancy score based on how well the seller info matches the keyword.
        :param seller_info: Dictionary containing seller data.
        :param keyword: The original search keyword.
        :return: An integer score (0-100).
        """
        score = 0
        keyword_lower = keyword.lower()

        product_desc_lower = seller_info["Product Title/Description"].lower()
        if product_desc_lower: # Ensure it's not empty
            if keyword_lower in product_desc_lower:
                score += 60
                score += min(10, product_desc_lower.count(keyword_lower) * 2)
            else:
                ratio = fuzz.partial_ratio(keyword_lower, product_desc_lower)
                score += int(ratio * 0.6)

        company_name_lower = seller_info["Company Name"].lower()
        if company_name_lower: # Ensure it's not empty
            if keyword_lower in company_name_lower:
                score += 30
            else:
                ratio = fuzz.partial_ratio(keyword_lower, company_name_lower)
                score += int(ratio * 0.3)

        if seller_info["Phone Number"]:
            score += 3
        if seller_info["Email"]: # Bonus for email
            score += 2
        if seller_info["Address"]:
            score += 5
        if seller_info["Product Catalog URL"]: # Bonus for catalog
            score += 5

        return min(100, score)

    def scrape_search_results(self, keyword, min_leads=100):
        """
        Scrapes search results to collect leads until min_leads are collected or no more pages.
        :param keyword: The keyword used for the search.
        :return: A list of collected leads.
        """
        page_num = 1
        self.leads = [] # Reset leads list for a new scrape
        
        # Store the handle of the search results page once it's active
        search_results_window_handle = self.driver.current_window_handle

        while len(self.leads) < min_leads: # Use len(self.leads) for condition
            self.logger.info(f"Scraping page {page_num}...")
            print(f"Scraping page {page_num}...")

            try:
                # Ensure the driver is on the correct search results window
                self.driver.switch_to.window(search_results_window_handle)
                self.logger.info(f"Ensured driver is on search results window: {self.driver.current_url}")

                # Wait for the main container of listing cards to be present
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "listingCardContainer"))
                )
                self.logger.info("Found listingCardContainer.")
                time.sleep(random.uniform(2, 4)) # Additional wait for dynamic content within the container

                # --- Logic for "Show more results" button ---
                self.logger.info("Attempting to click 'Show more results' button repeatedly.")
                while True:
                    try:
                        show_more_button = WebDriverWait(self.driver, 5).until( # Short wait for button visibility
                            EC.element_to_be_clickable((By.CSS_SELECTOR, ".showmoreresultsdiv button"))
                        )
                        show_more_button.click()
                        self.logger.info("Clicked 'Show more results' button.")
                        time.sleep(random.uniform(2, 4)) # Wait for new results to load
                    except (TimeoutException, NoSuchElementException):
                        self.logger.info("'Show more results' button no longer visible or timed out.")
                        break # Exit loop if button is not found or not clickable
                    except Exception as e:
                        self.logger.error(f"Error clicking 'Show more results': {e}")
                        break # Exit loop on unexpected error
                self.logger.info("Finished clicking 'Show more results' buttons.")
                # --- End of "Show more results" button logic ---

                # Find all individual product cards within the container AFTER clicking "Show more results"
                seller_elements = self.driver.find_elements(By.CSS_SELECTOR, ".listingCardContainer .card")
                
                if not seller_elements:
                    self.logger.warning(f"No product 'card' listings found on page {page_num}. Taking screenshot for debugging...")
                    self.driver.save_screenshot(f"search_results_page_{page_num}_no_listings.png")
                    print("No more results found or listings structure changed.")
                    break # Exit if no elements found on current page

                self.logger.info(f"Found {len(seller_elements)} listings on page {page_num}")
                print(f"Found {len(seller_elements)} listings on this page.")

                # --- New logic: Collect basic info and URLs first, then process detailed ---
                leads_to_process_from_current_page = []
                for seller_element in seller_elements:
                    # Extract basic info from the listing card (no new tabs opened here)
                    basic_seller_info = self._extract_seller_info_from_listing(seller_element)
                    leads_to_process_from_current_page.append(basic_seller_info)

                self.logger.info(f"Processing {len(leads_to_process_from_current_page)} leads for detailed info from page {page_num}.")
                
                for seller_info in leads_to_process_from_current_page:
                    if len(self.leads) >= min_leads:
                        break # Stop if minimum leads reached during detailed processing

                    time.sleep(random.uniform(0.5, 1.5)) # Shorter delay for individual element processing

                    # If phone, email, or catalog URL were NOT found on the listing card, try to get them from the profile page
                    # This is where the new tab will be opened and closed
                    if (not seller_info.get("Phone Number") or not seller_info.get("Email") or not seller_info.get("Product Catalog URL")):
                        # Pass the search_results_window_handle to the detailed extraction method
                        self._extract_detailed_info_from_profile(seller_info, search_results_window_handle)

                    # Calculate relevancy score
                    seller_info["Relevancy Score (%)"] = self._calculate_relevancy_score(seller_info, keyword)

                    # Add to leads list if we have at least company name or product description
                    if seller_info["Company Name"] or seller_info["Product Title/Description"]:
                        self.leads.append(sanitize_data(seller_info)) # Sanitize before adding
                        print(f"Collected lead {len(self.leads)}: {seller_info['Company Name'] or seller_info['Product Title/Description']} (Score: {seller_info['Relevancy Score (%)']}%)")

                # Pagination: Try to find and click the "Next" button
                # This logic remains, but it will be executed after all "Show more results" clicks and detailed info extraction on the current page.
                if len(self.leads) < min_leads:
                    try:
                        # Ensure we are on the search results window before trying to click Next
                        self.driver.switch_to.window(search_results_window_handle)
                        next_button = WebDriverWait(self.driver, 7).until(
                            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Next') or @class='next' or @class='pagination__next'] | //span[text()='Next'] | //*[contains(@class, 'pg-next')]"))
                        )
                        next_button.click()
                        page_num += 1
                        time.sleep(random.uniform(3, 5)) # Wait for the next page to fully load
                    except (TimeoutException, NoSuchElementException):
                        self.logger.info("No more 'Next' page buttons found.")
                        print("No more pages available.")
                        break # Exit loop if no next button

            except TimeoutException:
                self.logger.error(f"Timed out waiting for elements on page {page_num}.")
                self.driver.save_screenshot(f"page_{page_num}_timeout.png")
                break
            except Exception as e:
                self.logger.error(f"Error scraping search results on page {page_num}: {e}")
                self.driver.save_screenshot(f"page_{page_num}_error.png")
                break

        self.logger.info(f"Total leads collected: {len(self.leads)}")
        print(f"Total leads collected: {len(self.leads)}")
        return self.leads

    def export_to_csv(self, filename="leads.csv"):
        """
        Exports the collected leads to a CSV file.
        :param filename: Name of the output CSV file.
        :return: True if export was successful, False otherwise.
        """
        if not self.leads:
            self.logger.warning("No leads to export.")
            print("No leads to export.")
            return False

        try:
            # Define all possible fields, ensuring new ones are included
            fields = [
                "Company Name",
                "Product Title/Description",
                "Price",
                "Address",
                "Phone Number",
                "Email",
                "Product Catalog URL", # New field
                "Company Profile URL", # Renamed from Seller Page URL for consistency
                "Relevancy Score (%)"
            ]

            # Sort leads by relevancy score (highest first)
            sorted_leads = sorted(self.leads, key=lambda x: x.get("Relevancy Score (%)", 0), reverse=True)

            df = pd.DataFrame(sorted_leads)
            # Reindex to ensure desired column order and handle missing columns if any lead doesn't have a field
            df = df.reindex(columns=fields, fill_value="")

            df.to_csv(filename, index=False, encoding='utf-8-sig')
            self.logger.info(f"Successfully exported {len(sorted_leads)} leads to {filename}")
            return True
        except Exception as e:
            self.logger.error(f"Error exporting to CSV: {e}")
            print(f"Failed to export leads to CSV: {e}")
            return False

    def close(self):
        """Closes the browser and cleans up WebDriver resources."""
        if self.driver:
            # Get all window handles
            all_handles = self.driver.window_handles
            # Close all tabs except the first one (main window)
            if len(all_handles) > 1:
                for handle in all_handles[1:]: # Iterate from the second handle onwards
                    try:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                        self.logger.info(f"Closed extra tab: {handle}")
                    except WebDriverException as e:
                        self.logger.warning(f"Could not close window {handle}: {e}")
            
            # Switch back to the original main window and quit the browser
            try:
                self.driver.switch_to.window(all_handles[0])
                self.driver.quit()
                self.logger.info("Browser closed.")
                print("Browser closed.")
            except WebDriverException as e:
                self.logger.error(f"Error quitting main browser window: {e}")
                print(f"Error quitting browser: {e}")


    def run(self):
        """Main entry point for the CLI, orchestrating the scraping process."""
        parser = argparse.ArgumentParser(description="IndiaMART Lead Scraper - Extract leads based on keywords")
        # Set default keyword to "Cricket Ball"
        parser.add_argument("--keyword", "-k", type=str, default="Cricket Ball", help="Product keyword to search for (default: 'Cricket Ball')")
        parser.add_argument("--output", "-o", type=str, default="leads.csv", help="Output CSV file name (default: leads.csv)")
        parser.add_argument("--min-leads", "-m", type=int, default=50, help="Minimum number of leads to collect (default: 50)")
        parser.add_argument("--headless", "-H", action="store_true", help="Run in headless mode (no browser UI)")
        args = parser.parse_args()

        # Update scraper's headless setting based on CLI arg
        self.headless = args.headless
        # Re-setup driver if headless mode changes or it wasn't set up initially
        if not self.driver or (self.headless and "--headless=new" not in self.driver.service.service_args):
             self.close() # Close existing driver if any
             self._setup_driver()


        self.logger.info("Starting IndiaMART Lead Scraper")
        print("Initializing browser...")

        try:
            print("Browser initialized successfully.")

            print("\nNavigating to IndiaMART for login...")
            login_success = self.login()

            if login_success:
                print("\nLogin successful!")
                # Keyword will now default to "Cricket Ball" if not provided via CLI
                keyword = args.keyword 
                # Removed the input prompt for keyword, as it's now defaulted or taken from CLI

                self.logger.info(f"Using keyword: {keyword}")
                print(f"\nSearching for '{keyword}'...")

                search_success = self.search_product(keyword)

                if search_success:
                    print("\nSearch successful! Starting to collect leads...")
                    # Now scrape_search_results will operate on the new tab directly
                    leads = self.scrape_search_results(keyword, min_leads=args.min_leads)

                    if leads:
                        export_success = self.export_to_csv(filename=args.output)
                        if export_success:
                            print(f"\nScraping completed! {len(leads)} leads have been exported to {args.output}")
                        else:
                            print("\nFailed to export leads to CSV. Check logs for details.")
                    else:
                        print("\nNo leads were collected. Try a different keyword or check if the website structure has changed.")
                        self.logger.warning("No leads were collected.")
                else:
                    print("\nSearch failed. Please try again with a different keyword.")
                    self.logger.error("Search failed.")
            else:
                print("\nLogin failed. Please check your credentials and try again.")
                self.logger.error("Login failed.")

        except KeyboardInterrupt:
            self.logger.info("Operation cancelled by user.")
            print("\nOperation cancelled by user.")
        except Exception as e:
            self.logger.critical(f"A critical error occurred: {e}", exc_info=True)
            print(f"\nAn error occurred: {e}")
            print("Check the 'logs' directory for more details.")
        finally:
            self.close() # Ensure all browser windows are closed at the end

if __name__ == "__main__":
    # You can set your mobile number here or leave as None to be prompted
    # scraper_app = IndiaMartScraper(headless=False, mobile_number="YOUR_MOBILE_NUMBER")
    scraper_app = IndiaMartScraper(headless=False, mobile_number=None)
    scraper_app.run()
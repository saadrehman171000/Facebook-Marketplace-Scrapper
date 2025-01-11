import streamlit as st
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import re
import pandas as pd
import time
from fuzzywuzzy import fuzz
import zipfile
import io

def setup_chrome_options():
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    return chrome_options

def scrape_facebook_marketplace(city, product, min_price, max_price, city_code_fb, exact, sleep_time=5):
    chrome_options = setup_chrome_options()
    
    try:
        browser = uc.Chrome(options=chrome_options)
        browser.set_page_load_timeout(30)  # Set timeout to 30 seconds
    except Exception as e:
        st.error(f"Failed to initialize Chrome: {str(e)}")
        return pd.DataFrame(), 0

    try:
        # Setup URL
        exact_param = 'true' if exact else 'false'
        url = f"https://www.facebook.com/marketplace/{city_code_fb}/search?query={product}&minPrice={min_price}&maxPrice={max_price}&daysSinceListed=1&exact={exact_param}"
        browser.get(url)

        # Reduced sleep time and scroll count
        time.sleep(2)
        
        # Scroll only 3 times instead of 8
        for _ in range(3):
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        html = browser.page_source
        browser.quit()
        
        # Use BeautifulSoup to parse the HTML
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a')

        # Filter links based on search criteria
        if exact:
            final_links = []
            for link in links:
                if fuzz.partial_ratio(product.lower(), link.text.lower()) >= 90:
                    if fuzz.partial_ratio(city.lower().rstrip(), link.text.lower()) >= 70:
                        final_links.append(link)
        else:
            fuzz_threshold = 70
            final_links = [
                link for link in links
                if fuzz.partial_ratio(product.lower(), link.text.lower()) > fuzz_threshold and city.lower() in link.text.lower()
            ]

        # Extract product data
        extracted_data = []
        for prod_link in final_links:
            url = prod_link.get('href')
            text = '\n'.join(prod_link.stripped_strings)
            lines = text.split('\n')

            numeric_pattern = re.compile(r'\d[\d, •]*')
            price = None

            for line in lines:
                match = numeric_pattern.search(line)
                if match:
                    price_str = match.group()
                    price = float(price_str.replace(',', ''))
                    break

            title = lines[-2] if len(lines) > 1 else ""
            location = lines[-1] if lines else ""

            extracted_data.append({
                'title': title,
                'price': price,
                'location': location,
                'url': url
            })

        base = "https://web.facebook.com/"
        for items in extracted_data:
            items['url'] = base + items['url']

        # Create a DataFrame
        items_df = pd.DataFrame(extracted_data)
        return items_df, len(links)

    except Exception as e:
        st.error(f"Error during scraping: {str(e)}")
        browser.quit()
        return pd.DataFrame(), 0

# Streamlit UI
st.set_page_config(page_title="Facebook Marketplace Scraper", layout="wide")
st.title("🏷️ Facebook Marketplace Scraper")
st.markdown("""Welcome to the Facebook Marketplace Scraper!  
Easily find products in your city and filter by price.""")

# Initialize session state for storing marketplaces and results
if "marketplaces" not in st.session_state:
    st.session_state["marketplaces"] = []

if "scraped_data" not in st.session_state:
    st.session_state["scraped_data"] = None

# Input fields with better layout and styling
with st.form(key='input_form'):
    col1, col2 = st.columns(2)
    
    with col1:
        city = st.text_input("City", placeholder="Enter city name...")
        product = st.text_input("Product", placeholder="What are you looking for?")
    
    with col2:
        min_price = st.number_input("Minimum Price", min_value=0, value=0, step=1)
        max_price = st.number_input("Maximum Price", min_value=0, value=1000, step=1)
    
    city_code_fb = st.text_input("City Code for Facebook Marketplace", placeholder="Enter city code...")
    sleep_time = st.number_input("Sleep Time (seconds)", min_value=0.0, value=2.0, step=0.1)

    col3, col4 = st.columns([3, 1])
    with col3:
        submit_button = st.form_submit_button(label="🔍 Scrape Data")
    with col4:
        add_button = st.form_submit_button(label="🟢 Add")

# Handle adding a new marketplace
if add_button:
    if city and product and min_price <= max_price and city_code_fb:
        st.session_state["marketplaces"].append({
            "city": city,
            "product": product,
            "min_price": min_price,
            "max_price": max_price,
            "city_code_fb": city_code_fb,
            "sleep_time": sleep_time,
        })
        st.success("Marketplace added successfully!")
    else:
        st.error("Please fill all fields correctly.")

# Show the current list of marketplaces
if st.session_state["marketplaces"]:
    st.write("### Current Marketplaces:")
    for i, entry in enumerate(st.session_state["marketplaces"]):
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        col1.write(entry["city"])
        col2.write(entry["product"])
        col3.write(entry["min_price"])
        col4.write(entry["max_price"])
        col5.write(entry["city_code_fb"])
        col6.write(entry["sleep_time"])
        if col7.button("❌ Remove", key=f"remove_{i}"):
            st.session_state["marketplaces"].pop(i)

# Handle scraping data
if submit_button:
    st.session_state["scraped_data"] = None
    individual_files = []

    if not st.session_state["marketplaces"]:
        st.error("Please add at least one marketplace to scrape data.")
    else:
        combined_df = pd.DataFrame()
        for marketplace in st.session_state["marketplaces"]:
            with st.spinner(f"Scraping data for {marketplace['city']}..."):
                items_df, total_links = scrape_facebook_marketplace(
                    marketplace["city"],
                    marketplace["product"],
                    marketplace["min_price"],
                    marketplace["max_price"],
                    marketplace["city_code_fb"],
                    marketplace["sleep_time"]
                )

            if not items_df.empty:
                if "scraped_data" not in st.session_state:
                    st.session_state["scraped_data"] = pd.DataFrame()

                st.session_state["scraped_data"] = pd.concat([st.session_state["scraped_data"], items_df], ignore_index=True)

                # Save individual result for each marketplace
                individual_file = io.StringIO()
                items_df.to_csv(individual_file, index=False)
                individual_file.seek(0)
                individual_files.append({
                    'name': f"{marketplace['city']}_{marketplace['product']}_result.csv",
                    'file': individual_file
                })

        if st.session_state["scraped_data"] is not None and not st.session_state["scraped_data"].empty:
            st.write("### Combined Match Results:")
            st.dataframe(st.session_state["scraped_data"])

            # Save combined CSV file
            combined_file = io.StringIO()
            st.session_state["scraped_data"].to_csv(combined_file, index=False)
            combined_file.seek(0)

            # Zip all individual and combined files into one package
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_data in individual_files:
                    zip_file.writestr(file_data['name'], file_data['file'].getvalue())
                zip_file.writestr("combined_results.csv", combined_file.getvalue())

            zip_buffer.seek(0)

            # Add download button
            st.download_button(
                label="Download All Results",
                data=zip_buffer,
                file_name="scraped_results.zip",
                mime="application/zip"
            )

from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pdfplumber
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form.get('url')
        data_type = request.form.get('data_type')
    
        if url and data_type == 'table':
            tables = scrape_tables(url)
            if tables:
                if 'table_number' in request.form:
                    selected_tables = request.form.getlist('table_number')
                    selected_tables = [int(i) for i in selected_tables]
                    return render_template('index.html', tables=tables, url=url, 
                                        selected_tables=selected_tables, data_type='table')
                return render_template('index.html', tables=tables, url=url, data_type='table')
            else:
                return render_template('index.html', error="No tables found on this page.", url=url, data_type='table')

        elif url and data_type == 'image':
            image_format = request.form.get('image_format', 'all')
            num_images = request.form.get('num_images')
            images = scrape_images(url, image_format)
            if images:
                if num_images:
                    try:
                        num_images = int(num_images)
                        images = images[:num_images]
                    except ValueError:
                        pass
                return render_template('index.html', images=images, url=url, 
                                     data_type='image', image_format=image_format,
                                     num_images=num_images or len(images))
            else:
                return render_template('index.html', error="No images found on this page.", url=url, data_type='image')

        elif url and data_type == 'movie':
            movie_data = scrape_movie_details(url)
            if "error" in movie_data:
                return render_template('index.html', error=movie_data["error"], data_type='movie')
            else:
                return render_template('index.html', movie_data=movie_data, data_type='movie')
            
        elif url and data_type == 'video':
            video_format = request.form.get('video_format', 'all')
            num_videos = request.form.get('num_videos')
            video_data = scrape_videos(url, video_format)
            if video_data:
                if num_videos:
                    try:
                        num_videos = int(num_videos)
                        video_data = video_data[:num_videos]
                    except ValueError:
                        pass
                return render_template('index.html', video_data=video_data, url=url, 
                                     data_type='video', video_format=video_format,
                                     num_videos=num_videos or len(video_data))
            else:
                return render_template('index.html', error="No videos found on this page.", url=url, data_type='video')

        elif url and data_type == 'ebay':
            product_name = request.form.get('url')  # Use 'url' field for product name
            num_products = request.form.get('num_products')
            if product_name:
                product_details = scrape_ebay_product(product_name)
                if product_details:
                    if num_products:
                        try:
                            num_products = int(num_products)
                            product_details = product_details[:num_products]
                        except ValueError:
                            pass
                    return render_template('index.html', product_details=product_details, url=product_name, 
                                         data_type='ebay', num_products=num_products or len(product_details))
                else:
                    return render_template('index.html', error="No products found on eBay.", data_type='ebay')
            else:
                return render_template('index.html', error="Please enter a product name.", data_type='ebay')

        elif url and data_type == 'news':
            num_headlines = request.form.get('num_headlines')
            headlines = scrape_news_headlines(url)
            if headlines:
                if num_headlines:
                    try:
                        num_headlines = int(num_headlines)
                        headlines = headlines[:num_headlines]
                    except ValueError:
                        pass
                return render_template('index.html', headlines=headlines, url=url, 
                                     data_type='news', num_headlines=num_headlines or len(headlines))
            else:
                return render_template('index.html', error="No verified headlines found on this page.", url=url, data_type='news')

        elif url and data_type == 'pdf':
            pdf_links = scrape_pdf_links(url)
            if pdf_links:
                return render_template('index.html', pdf_links=pdf_links, url=url, data_type='pdf')
            else:
                return render_template('index.html', error="No PDF files found on this page.", url=url, data_type='pdf')

    return render_template('index.html', tables=None, images=None, movie_data=None, video_data=None, headlines=None, pdf_links=None, product_details=None, error=None)

@app.route('/extract_pdf_info', methods=['POST'])
def extract_pdf_info():
    """Extract text and metadata from a PDF URL."""
    pdf_url = request.form.get('pdf_url')
    try:
        # Download the PDF
        response = requests.get(pdf_url, timeout=10)
        response.raise_for_status()
        
        # Save PDF temporarily
        temp_file = 'temp.pdf'
        with open(temp_file, 'wb') as f:
            f.write(response.content)
        
        # Extract text and metadata using pdfplumber
        with pdfplumber.open(temp_file) as pdf:
            # Extract text
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            # Extract metadata (if available)
            metadata = pdf.metadata if pdf.metadata else {}
            title = metadata.get('Title', 'N/A')
            author = metadata.get('Author', 'N/A')
            page_count = len(pdf.pages)
        
        # Clean up
        os.remove(temp_file)
        
        return jsonify({
            'success': True,
            'text': text,  # Return full text
            'title': title,
            'author': author,
            'page_count': page_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def scrape_tables(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        table_data = []
        for table in tables:
            rows = table.find_all('tr')
            table_rows = []
            for row in rows:
                columns = row.find_all('td')
                columns = [col.text.strip() for col in columns]
                if columns:
                    table_rows.append(columns)
            if table_rows:
                table_data.append(table_rows)
        return table_data
    except requests.exceptions.RequestException:
        return None

def scrape_images(url, image_format):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        images = soup.find_all('img')
        allowed_formats = {'png': ['.png'], 'jpg': ['.jpg', '.jpeg'], 'all': ['.png', '.jpg', '.jpeg']}
        image_urls = []
        for img in images:
            img_url = img.get('src')
            if img_url and any(img_url.endswith(ext) for ext in allowed_formats[image_format]):
                if img_url.startswith('http'):
                    image_urls.append(img_url)
                else:
                    base_url = url.rsplit('/', 1)[0]
                    full_url = os.path.join(base_url, img_url)
                    image_urls.append(full_url)
        return image_urls
    except requests.exceptions.RequestException:
        return None

def scrape_movie_details(movie_name):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        search_url = f"https://www.imdb.com/find?q={movie_name.replace(' ', '+')}&ref_=nv_sr_sm"
        search_response = requests.get(search_url, headers=headers, timeout=10)
        search_response.raise_for_status()
        search_soup = BeautifulSoup(search_response.content, 'html.parser')
        first_result = search_soup.select_one('.ipc-metadata-list-summary-item a.ipc-metadata-list-summary-item__t')
        if not first_result:
            return {"error": "No movie found with that name."}
        movie_url = "https://www.imdb.com" + first_result['href']
        movie_response = requests.get(movie_url, headers=headers, timeout=10)
        movie_response.raise_for_status()
        soup = BeautifulSoup(movie_response.content, 'html.parser')
        title = soup.select_one('h1').text.strip()
        poster = soup.select_one('img.ipc-image')
        poster_url = poster['src'] if poster else "N/A"
        year_elem = soup.select_one('a[href*="/releaseinfo"]')
        year = year_elem.text.strip() if year_elem else "N/A"
        rating_elem = soup.select_one('div[data-testid="hero-rating-bar__aggregate-rating__score"] span')
        rating = rating_elem.text.strip() + "/10" if rating_elem else "N/A"
        plot_elem = soup.select_one('[data-testid="plot"]')
        plot = plot_elem.text.strip() if plot_elem else "N/A"
        genre_elem = soup.select_one('.ipc-chip.ipc-chip--on-baseAlt .ipc-chip__text')
        genre = genre_elem.text.strip() if genre_elem else "N/A"
        return {
            "name": title,
            "poster_url": poster_url,
            "year": year,
            "rating": rating,
            "plot": plot,
            "genre": genre
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error occurred: {e}"}
    except Exception as e:
        return {"error": f"An error occurred: {e}"}

def scrape_videos(url, video_format):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        videos = soup.find_all('video')
        video_urls = []
        for video in videos:
            video_sources = video.find_all('source')
            for source in video_sources:
                video_url = source.get('src')
                if video_url:
                    if video_format != 'all' and not video_url.endswith(video_format):
                        continue
                    if video_url.startswith('http'):
                        video_urls.append(video_url)
                    else:
                        base_url = url.rsplit('/', 1)[0]
                        full_url = os.path.join(base_url, video_url)
                        video_urls.append(full_url)
        return video_urls
    except requests.exceptions.RequestException:
        return None

def scrape_news_headlines(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        headlines = soup.find_all(['h1', 'h2', 'h3'])
        if not headlines:
            headlines = soup.find_all('a', class_=lambda x: x and ('excerpt' in x.lower() or 'title' in x.lower() or 'headline' in x.lower()))
        if not headlines:
            headlines = soup.find_all('a')
        def is_valid_headline(text):
            if len(text) < 15:
                return False
            non_headline_phrases = [
                'home', 'about', 'contact', 'login', 'register', "today's gallery", "The Daily Star - Bangladesh News, Political News, Bangladesh Economy & Videos, Breaking News"
            ]
            if any(phrase.lower() in text.lower() for phrase in non_headline_phrases):
                return False
            if re.search(r'\d', text) or re.search(r'[A-Z][a-z]+', text):
                return True
            return True
        headline_texts = []
        for headline in headlines:
            text = headline.get_text().strip()
            if text and is_valid_headline(text) and text not in headline_texts:
                headline_texts.append(text)
        return headline_texts if headline_texts else None
    except requests.exceptions.RequestException:
        return None

def scrape_ebay_product(product_name):
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={product_name.replace(' ', '+')}&_sop=12"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.ebay.com/"
    }
    
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        product_details = []
        product_listings = soup.find_all('li', {'class': 's-item s-item__pl-on-bottom'})

        if not product_listings:
            print(f"No listings found for '{product_name}'. Check selector or eBay response.")
            print(f"Response snippet: {response.text[:500]}")
            return []

        for product in product_listings[2:]:
            try:
                title = product.find('div', {'class': 's-item__title'}).text.strip()
                link = product.find('a', {'class': 's-item__link'})['href']
                
                # Improved image extraction
                image_elem = product.find('img')
                image_url = None
                if image_elem:
                    # Check multiple possible attributes for the image source
                    image_url = image_elem.get('src') or image_elem.get('data-src') or image_elem.get('srcset')
                    if image_url and 'srcset' in image_elem.attrs:
                        # Handle srcset by taking the first URL
                        image_url = image_url.split(',')[0].split()[0]
                    if image_url and not image_url.startswith('http'):
                        image_url = f"https:{image_url}"
                # Fallback if no image is found
                image_url = image_url if image_url else "https://via.placeholder.com/150?text=No+Image"

                price = product.find('span', {'class': 's-item__price'}).text.strip() if product.find('span', {'class': 's-item__price'}) else 'Price not available'
                rating = product.find('div', {'class': 'x-star-rating'}).text.strip() if product.find('div', {'class': 'x-star-rating'}) else 'No rating'
                
                product_details.append({
                    "title": title,
                    "link": link,
                    "image_url": image_url,
                    "price": price,
                    "rating": rating
                })
                print(f"Extracted image URL: {image_url}")  # Debug output

            except AttributeError as e:
                print(f"Error parsing product: {e}")
                continue

        if not product_details:
            print(f"No valid product details extracted for '{product_name}'.")
        
        return product_details[:100]  # Limit to 10 results

    except requests.RequestException as e:
        print(f"Failed to fetch eBay page for '{product_name}': {e}")
        return []

def scrape_pdf_links(url):
    """Scrape a webpage for PDF links, first with BS4, then with Selenium if no PDFs are found."""
    # First, try with BeautifulSoup (faster for static content)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        pdf_links = []
        
        # Check <a> tags
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.lower().endswith('.pdf') and href.startswith(('http://', 'https://')):
                pdf_name = href.split('/')[-1].split('?')[0]  # Extract the PDF name, remove query params
                pdf_links.append({'url': href, 'name': pdf_name})
        
        # Check <source> tags
        for source in soup.find_all('source', src=True):
            src = source['src']
            if src.lower().endswith('.pdf') and src.startswith(('http://', 'https://')):
                pdf_name = src.split('/')[-1].split('?')[0]  # Extract the PDF name, remove query params
                pdf_links.append({'url': src, 'name': pdf_name})
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_pdf_links = []
        for link in pdf_links:
            if link['url'] not in seen_urls:
                seen_urls.add(link['url'])
                unique_pdf_links.append(link)
        
        if unique_pdf_links:
            logger.info(f"Found {len(unique_pdf_links)} PDFs with BeautifulSoup")
            return unique_pdf_links
    
    except requests.exceptions.RequestException as e:
        logger.error(f"BS4 request failed: {e}")
        return None

    # If no PDFs found with BS4, fall back to Selenium
    logger.info("No PDFs found with BS4, falling back to Selenium")
    
    options = Options()
     
    options.add_argument("--headless") # Use the proper headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(30)  # Increase page load timeout
        logger.info(f"Navigating to URL: {url}")
        driver.get(url)

        # Wait for the page to load and check for any button that might reveal PDFs (e.g., "Documents", "Resources", etc.)
        try:
            # Look for buttons that might reveal PDFs (e.g., "Documents", "Resources", "Show More")
            potential_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Documents') or contains(text(), 'Resources') or contains(text(), 'Show More')]")
            for button in potential_buttons:
                try:
                    logger.info(f"Clicking button with text: {button.text}")
                    button.click()
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "a"))
                    )  # Wait for any <a> tags to appear
                    break  # Stop after clicking the first relevant button
                except Exception as e:
                    logger.warning(f"Could not click button '{button.text}': {e}")
        except Exception as e:
            logger.warning(f"No relevant buttons found to click: {e}")

        # Wait for any <a> tags to ensure the page is fully loaded
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "a"))
            )
            logger.info("Page loaded successfully with Selenium")
        except Exception as e:
            logger.error(f"Failed to load page with Selenium: {e}")
            return None

        # Parse the page source with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        pdf_links = []
        
        # Check all <a> tags for PDF links
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.lower().endswith('.pdf') and href.startswith(('http://', 'https://')):
                pdf_name = href.split('/')[-1].split('?')[0]  # Extract the PDF name, remove query params
                pdf_links.append({'url': href, 'name': pdf_name})
        
        # Check <source> tags
        for source in soup.find_all('source', src=True):
            src = source['src']
            if src.lower().endswith('.pdf') and src.startswith(('http://', 'https://')):
                pdf_name = src.split('/')[-1].split('?')[0]  # Extract the PDF name, remove query params
                pdf_links.append({'url': src, 'name': pdf_name})
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_pdf_links = []
        for link in pdf_links:
            if link['url'] not in seen_urls:
                seen_urls.add(link['url'])
                unique_pdf_links.append(link)
        
        if unique_pdf_links:
            logger.info(f"Found {len(unique_pdf_links)} PDFs with Selenium")
        else:
            logger.info("No PDFs found with Selenium")
        
        return unique_pdf_links if unique_pdf_links else None
    
    except Exception as e:
        logger.error(f"Error scraping PDFs with Selenium: {e}")
        return None
    finally:
        if driver:
            driver.quit()
            logger.info("Selenium driver closed")

if __name__ == '__main__':
    app.run(debug=True)
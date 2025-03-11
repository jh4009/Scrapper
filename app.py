from flask import Flask, render_template, request, jsonify, send_file, make_response
import requests
from bs4 import BeautifulSoup
import os
import io
import zipfile
import csv
from functools import lru_cache
import json
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pdfplumber
from urllib.parse import urljoin

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add configuration for rate limiting and caching ---
# from flask_limiter import Limiter
# from flask_limiter.util import get_remote_address
# limiter = Limiter(get_remote_address, app=app, default_limits=["100 per day", "10 per hour"])


# Cached scraping functions
@lru_cache(maxsize=100)
def scrape_tables_cached(url):
    return scrape_tables(url)

def scrape_tables(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        table_data = []
        for table in tables:
            rows = table.find_all('tr')
            table_rows = [[col.text.strip() for col in row.find_all( 'td')] for row in rows if row.find_all( 'td')]
            if table_rows:
                table_data.append(table_rows)
        return table_data
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def scrape_images(url, image_format):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        # Include both <img> and <image> tags
        images = soup.find_all(['img', 'image'])
        allowed_formats = {
            'png': ['.png'],
            'jpg': ['.jpg', '.jpeg'],
            'webp': ['.webp'],
            'gif': ['.gif'],
            'all': ['.png', '.jpg', '.jpeg', '.webp', '.gif']
        }
        image_urls = []
        for img in images:
            # Check multiple attributes for image source
            img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if img_url and any(img_url.lower().endswith(ext) for ext in allowed_formats[image_format]):
                full_url = urljoin(url, img_url)
                image_urls.append(full_url)
        if not image_urls:  # Fallback to Selenium for dynamic content
            logger.info(f"No images found with BS4 at {url}, trying Selenium")
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "img")))
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            images = soup.find_all(['img', 'image'])
            for img in images:
                img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if img_url and any(img_url.lower().endswith(ext) for ext in allowed_formats[image_format]):
                    full_url = urljoin(url, img_url)
                    image_urls.append(full_url)
            driver.quit()
        return image_urls if image_urls else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


def scrape_movie_details(movie_name):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    try:
        # IMDb search URL
        search_url = f"https://www.imdb.com/find?q={movie_name.replace(' ', '+')}&ref_=nv_sr_sm"
        search_response = requests.get(search_url, headers=headers, timeout=10)
        search_response.raise_for_status()
        
        search_soup = BeautifulSoup(search_response.content, 'html.parser')
        first_result = search_soup.select_one('.ipc-metadata-list-summary-item a')
        if not first_result:
            return {"error": "No movie found with that name."}
        
        movie_url = "https://www.imdb.com" + first_result.get('href', '')
        movie_response = requests.get(movie_url, headers=headers, timeout=10)
        movie_response.raise_for_status()
        
        soup = BeautifulSoup(movie_response.content, 'html.parser')
        
        # Extracting Title
        title_elem = soup.select_one('h1')
        title = title_elem.text.strip() if title_elem else "N/A"
        
        # Extracting Poster URL
        poster_elem = soup.select_one('img.ipc-image')
        poster_url = poster_elem.get('src', "N/A") if poster_elem else "N/A"
        
        # Extracting Year
        year_elem = soup.select_one('a[href*="/releaseinfo"]')
        year = year_elem.text.strip() if year_elem else "N/A"
        
        # Extracting Rating
        rating_elem = soup.select_one('div[data-testid="hero-rating-bar__aggregate-rating__score"] span')
        rating = f"{rating_elem.text.strip()}/10" if rating_elem else "N/A"
        
        # Extracting Plot (more specific and avoiding duplicates)
        plot_elem = soup.select_one('span[data-testid="plot-xl"]')
        plot = plot_elem.text.strip() if plot_elem else "N/A"
        
        # Extracting Genresss (Multiple if available)
        genre_elems = soup.select('.ipc-chip__text')
        genres = [genre.text.strip() for genre in genre_elems] if genre_elems else ["N/A"]
        
        runtime_elem = soup.select_one('li[data-testid="title-techspec_runtime"] div')
        runtime = runtime_elem.text.strip() if runtime_elem else "N/A"

        return {
            "name": title,
            "poster_url": poster_url,
            "year": year,
            "rating": rating,
            "plot": plot,
            "genre": ', '.join(genres),
            "movie_link": movie_url
        }
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {e}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}

    
def scrape_book_details(book_name):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124"}
    try:
        # Step 1: Search OpenLibrary for the book
        search_url = f"https://openlibrary.org/search?q={book_name.replace(' ', '+')}&mode=everything"
        search_response = requests.get(search_url, headers=headers, timeout=10)
        search_response.raise_for_status()
        search_soup = BeautifulSoup(search_response.content, 'html.parser')
        first_result = search_soup.select_one('li.searchResultItem')
        if not first_result:
            return {"error": "No book found with that name."}
        
        # Extract basic details from search result
        title_elem = first_result.select_one('h3.booktitle a')
        title = title_elem.text.strip() if title_elem else "N/A"

        cover_elem = first_result.select_one('span.bookcover img')
        cover_url = "https:" + cover_elem['src'] if cover_elem else "N/A"

        author_elem = first_result.select_one('span.bookauthor a')
        author = author_elem.text.strip() if author_elem else "N/A"

        year_elem = first_result.select_one('span.resultDetails span')
        year = year_elem.text.strip().replace("First published in ", "") if year_elem else "N/A"

        rating_elem = first_result.select_one('span.ratingsByline span[itemprop="ratingValue"]')
        rating = rating_elem.text.strip() if rating_elem else "N/A"

        # Step 2: Follow the link to the detail page for description
        book_link = first_result.select_one('h3.booktitle a')['href']
        detail_url = f"https://openlibrary.org{book_link}"
        detail_response = requests.get(detail_url, headers=headers, timeout=10)
        detail_response.raise_for_status()
        detail_soup = BeautifulSoup(detail_response.content, 'html.parser')
        
        description_elem = detail_soup.select_one('div.read-more__content')
        if description_elem:
            paragraphs = [p.text.strip() for p in description_elem.find_all('p') if not p.find('a')]
            description = " ".join(paragraphs) if paragraphs else "N/A"
        else:
            description = "N/A"

        return {
            "name": title,
            "cover_url": cover_url,
            "author": author,
            "year": year,
            "rating": rating,
            "description": description,
            "book_link": detail_url # Add the detail URL to the response
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {e}"}
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
                    if not video_url.startswith('http'):
                        base_url = url.rsplit('/', 1)[0]
                        video_url = os.path.join(base_url, video_url)
                    video_urls.append(video_url)
        return tuple(video_urls)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def scrape_ebay_product(product_name):
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={product_name.replace(' ', '+')}&_sop=12"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    try:
        driver.get(search_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'li.s-item')))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        product_details = []
        product_listings = soup.select('li.s-item.s-item__pl-on-bottom')
        if not product_listings:
            logger.warning("No product listings found with standard selector, trying fallback.")
            product_listings = soup.select('li[data-viewport]')
        for product in product_listings[2:]:
            try:
                title_elem = product.select_one('.s-item__title')
                title = title_elem.text.strip() if title_elem else "N/A"
                link_elem = product.select_one('a.s-item__link')
                link = link_elem['href'] if link_elem else "N/A"
                image_elem = product.select_one('img')
                image_url = image_elem.get('src') if image_elem else "https://via.placeholder.com/150?text=No+Image"
                price_elem = product.select_one('.s-item__price')
                price = price_elem.text.strip() if price_elem else "N/A"
                rating_elem = product.select_one('.s-item__reviews')
                rating = rating_elem.text.strip() if rating_elem else "N/A"
                if title != "N/A" and link != "N/A":
                    product_details.append({
                        "title": title,
                        "link": link,
                        "image_url": image_url,
                        "price": price,
                        "rating": rating
                    })
            except AttributeError as e:
                logger.error(f"Error parsing product: {e}")
                continue
        if not product_details:
            logger.error("No valid products parsed from eBay.")
            return None
        logger.info(f"Scraped {len(product_details)} products from eBay for '{product_name}'")
        return product_details
    except Exception as e:
        logger.error(f"Error fetching eBay with Selenium: {e}")
        return None
    finally:
        driver.quit()

def scrape_news_headlines(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124"}
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
            if len(text) < 15 or any(phrase.lower() in text.lower() for phrase in ['home', 'about', 'contact', 'login', 'register']):
                return False
            return True
        headline_texts = []
        for headline in headlines:
            text = headline.get_text().strip()
            if text and is_valid_headline(text) and text not in headline_texts:
                headline_texts.append(text)
        return tuple(headline_texts) if headline_texts else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def scrape_pdf_links(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        pdf_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.lower().endswith('.pdf') and href.startswith(('http://', 'https://')):
                pdf_name = href.split('/')[-1].split('?')[0]
                pdf_links.append({'url': href, 'name': pdf_name})
        if pdf_links:
            seen_urls = set()
            unique_pdf_links = [link for link in pdf_links if not (link['url'] in seen_urls or seen_urls.add(link['url']))]
            return unique_pdf_links
    except requests.exceptions.RequestException as e:
        logger.error(f"BS4 request failed: {e}")

    logger.info("No PDFs found with BS4, falling back to Selenium")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        pdf_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.lower().endswith('.pdf'):
                if not href.startswith(('http://', 'https://')):
                    base_url = url.rsplit('/', 1)[0]
                    href = os.path.join(base_url, href)
                pdf_name = href.split('/')[-1].split('?')[0]
                pdf_links.append({'url': href, 'name': pdf_name})
        seen_urls = set()
        unique_pdf_links = [link for link in pdf_links if not (link['url'] in seen_urls or seen_urls.add(link['url']))]
        return unique_pdf_links if unique_pdf_links else None
    except Exception as e:
        logger.error(f"Error fetching PDFs with Selenium: {e}")
        return None
    finally:
        driver.quit()

@app.route('/extract_pdf_info', methods=['POST'])
def extract_pdf_info():
    pdf_url = request.form.get('pdf_url')
    try:
        response = requests.get(pdf_url, timeout=10)
        response.raise_for_status()
        with open('temp.pdf', 'wb') as f:
            f.write(response.content)
        with pdfplumber.open('temp.pdf') as pdf:
            text = "".join(page.extract_text() or "" for page in pdf.pages)
            metadata = pdf.metadata or {}
            title = metadata.get('Title', 'N/A')
            author = metadata.get('Author', 'N/A')
            page_count = len(pdf.pages)
        os.remove('temp.pdf')
        return jsonify({'success': True, 'text': text, 'title': title, 'author': author, 'page_count': page_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
@app.route('/send_to_api', methods=['POST'])
# @limiter.limit("5 per minute")
def send_to_api():
    api_link = request.form.get('api_link')
    url = request.form.get('url')
    data_type = request.form.get('data_type')
    num_items = request.form.get('num_items', type=int)

    if not api_link:
        return jsonify({'success': False, 'error': 'API link is required'})

    scrape_data = None

    if data_type == 'table':
        scrape_data = scrape_tables_cached(url)

    elif data_type == 'image':
        image_format = request.form.get('image_format', 'all')
        scrape_data = scrape_images(url, image_format)

    elif data_type == 'movie':
        scrape_data = scrape_movie_details(url)

    elif data_type == 'pdf':
        scrape_data = scrape_pdf_links(url)
    
    elif data_type == 'book':
        scrape_data = scrape_book_details(url)
    
    elif data_type == 'video':
        video_format = request.form.get('video_format', 'all')
        scrape_data = scrape_videos(url, video_format)
    
    elif data_type == 'ebay':
        scrape_data = scrape_ebay_product(url)
    
    elif data_type == 'news':
        scrape_data = scrape_news_headlines(url)

    if not scrape_data:
        return jsonify({'success': False, 'error': 'No data found.'})
    
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(api_link, json=scrape_data, headers=headers)
        response.raise_for_status()
        return jsonify({'success': True, 'message': 'Data sent to API successfully.'})
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'error': str(e)})
@app.route('/scrape', methods=['POST'])
# @limiter.limit("10 per minute")
def scrape():
    url = request.form.get('url')
    data_type = request.form.get('data_type')
    num_items = request.form.get('num_items', type=int)

    if data_type == 'table':
        tables = scrape_tables_cached(url)
        if tables:
            return jsonify({'success': True, 'tables': tables})
        return jsonify({'success': False, 'error': 'No tables found.'})

    elif data_type == 'image':
        image_format = request.form.get('image_format', 'all')
        images = scrape_images(url, image_format)
        if images:
            num_items = num_items or len(images)
            images = images[:min(int(num_items), len(images))]
            return jsonify({'success': True, 'images': list(images), 'image_format': image_format, 'total': len(images)})
        return jsonify({'success': False, 'error': 'No images found or failed to fetch URL'})

    elif data_type == 'movie':
        movie_data = scrape_movie_details(url)
        if "error" in movie_data:
            return jsonify({'success': False, 'error': movie_data["error"]})
        return jsonify({'success': True, 'movie_data': movie_data})
    
    elif data_type == 'book':
        book_data = scrape_book_details(url) 
        if "error" in book_data:
            return jsonify({'success': False, 'error': book_data["error"]})
        return jsonify({'success': True, 'book_data': book_data})

    elif data_type == 'video':
        video_format = request.form.get('video_format', 'all')
        videos = scrape_videos(url, video_format)
        if videos:
            num_items = num_items or len(videos)
            videos = videos[:min(int(num_items), len(videos))]
            return jsonify({'success': True, 'videos': list(videos), 'video_format': video_format, 'total': len(videos)})
        return jsonify({'success': False, 'error': 'No videos found.'})

    elif data_type == 'ebay':
        product_details = scrape_ebay_product(url)
        if product_details:
            num_items = num_items or len(product_details)
            product_details = product_details[:min(int(num_items), len(product_details))]
            return jsonify({'success': True, 'product_details': product_details, 'total': len(product_details)})
        return jsonify({'success': False, 'error': 'No products found on eBay.'})

    elif data_type == 'news':
        headlines = scrape_news_headlines(url)
        if headlines:
            num_items = num_items or len(headlines)
            headlines = headlines[:min(int(num_items), len(headlines))]
            return jsonify({'success': True, 'headlines': list(headlines), 'total': len(headlines)})
        return jsonify({'success': False, 'error': 'No headlines found.'})

    elif data_type == 'pdf':
        pdf_links = scrape_pdf_links(url)
        if pdf_links:
            num_items = num_items or len(pdf_links)
            pdf_links = pdf_links[:min(int(num_items), len(pdf_links))]
            return jsonify({'success': True, 'pdf_links': pdf_links, 'total': len(pdf_links)})
        return jsonify({'success': False, 'error': 'No PDFs found.'})

    return jsonify({'success': False, 'error': 'Invalid data type'})

@app.route('/', methods=['GET', 'POST'])
def index():
    history = json.loads(request.cookies.get('history', '[]'))

    if request.method == 'POST':
        url = request.form.get('url')
        data_type = request.form.get('data_type')
        if url and data_type:
            history.append((url, data_type))
            history = history[:5]
            resp = make_response(render_template('index.html', history=history))
            resp.set_cookie('history', json.dumps(history), max_age=3600 * 24 * 30)
            return resp

    return render_template('index.html', history=history)

@app.route('/export_csv', methods=['POST'])
def export_csv():
    url = request.form.get('url')
    selected_tables = request.form.getlist('table_number')
    tables = scrape_tables_cached(url)
    if not tables or not selected_tables:
        return jsonify({'success': False, 'error': 'No tables to export'})
    output = io.StringIO()
    writer = csv.writer(output)
    for idx in map(int, selected_tables):
        writer.writerow(['Table ' + str(idx + 1)])
        for row in tables[idx]:
            writer.writerow(row)
        writer.writerow([])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='tables.csv'
    )

@app.route('/export_images', methods=['POST'])
def export_images():
    url = request.form.get('url')
    image_format = request.form.get('image_format', 'all')
    num_items = request.form.get('num_items', type=int)
    images = scrape_images(url, image_format)
    if not images:
        return jsonify({'success': False, 'error': 'No images to export'})
    images = images[:num_items] if num_items else images
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, img_url in enumerate(images):
            try:
                img_data = requests.get(img_url, timeout=5).content
                img_name = f'image_{i + 1}.{img_url.split(".")[-1]}'
                zip_file.writestr(img_name, img_data)
            except Exception as e:
                logger.error(f"Failed to download {img_url}: {e}")
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='images.zip'
    )

if __name__ == '__main__':
    app.run(debug=True)
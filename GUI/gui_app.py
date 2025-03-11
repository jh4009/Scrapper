import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from bs4 import BeautifulSoup
import requests
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pdfplumber
import os
import io
import zipfile
import csv
from PIL import Image
import urllib.request
from functools import lru_cache
import pyperclip
import threading
import time
import webbrowser  # For opening links in the default browser

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Scraping Functions
@lru_cache(maxsize=100)
def scrape_tables(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        table_data = []
        for table in tables:
            rows = table.find_all('tr')
            table_rows = [[col.text.strip() for col in row.find_all(['td', 'th'])] for row in rows if row.find_all(['td', 'th'])]
            if table_rows:
                table_data.append(table_rows)
        return table_data
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

@lru_cache(maxsize=100)
def scrape_images(url, image_format):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        images = soup.find_all('img')
        allowed_formats = {'png': ['.png'], 'jpg': ['.jpg', '.jpeg'], 'all': ['.png', '.jpg', '.jpeg']}
        image_urls = []
        for img in images:
            img_url = img.get('src') or img.get('data-src')
            if img_url and any(img_url.endswith(ext) for ext in allowed_formats[image_format]):
                if not img_url.startswith('http'):
                    base_url = url.rsplit('/', 1)[0]
                    img_url = os.path.join(base_url, img_url)
                image_urls.append(img_url)
        return image_urls
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def scrape_movie_details(movie_name):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124"}
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
        return {"error": f"Network error: {e}"}

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
        return video_urls
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def scrape_ebay_product(product_name):
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={product_name.replace(' ', '+')}&_sop=12"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
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
        for product in product_listings:
            try:
                title_elem = product.select_one('.s-item__title')
                title = title_elem.text.strip() if title_elem else "N/A"
                link_elem = product.select_one('a.s-item__link')
                link = link_elem['href'] if link_elem else "N/A"
                image_elem = product.select_one('img')
                image_url = None
                if image_elem:
                    image_url = image_elem.get('data-src') or image_elem.get('src')
                image_url = image_url if image_url else "https://via.placeholder.com/150?text=No+Image"
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
        return headline_texts if headline_texts else None
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
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(30)
        logger.info(f"Navigating to URL: {url}")
        driver.get(url)

        try:
            potential_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Documents') or contains(text(), 'Resources') or contains(text(), 'Show More')]")
            for button in potential_buttons:
                try:
                    logger.info(f"Clicking button with text: {button.text}")
                    button.click()
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
                    break
                except Exception as e:
                    logger.warning(f"Could not click button '{button.text}': {e}")
        except Exception as e:
            logger.warning(f"No relevant buttons found to click: {e}")

        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
            logger.info("Page loaded successfully with Selenium")
        except Exception as e:
            logger.error(f"Failed to load page with Selenium: {e}")
            return None

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
        if driver:
            driver.quit()

def extract_pdf_info(pdf_url):
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
        return {'success': True, 'text': text, 'title': title, 'author': author, 'page_count': page_count}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Export and Download Functions
def export_tables_to_csv(tables):
    file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
    if not file_path:
        return
    try:
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for i, table in enumerate(tables):
                writer.writerow([f"Table {i + 1}"])
                for row in table:
                    writer.writerow(row)
                writer.writerow([])
        messagebox.showinfo("Success", f"Tables exported to {file_path}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to export tables: {e}")

def export_images_to_zip(images):
    file_path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP files", "*.zip")])
    if not file_path:
        return
    try:
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
        with open(file_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
        messagebox.showinfo("Success", f"Images exported to {file_path}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to export images: {e}")

def download_pdf(pdf_url, pdf_name):
    file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")], initialfile=pdf_name)
    if not file_path:
        return
    try:
        response = requests.get(pdf_url, timeout=10)
        response.raise_for_status()
        with open(file_path, 'wb') as f:
            f.write(response.content)
        messagebox.showinfo("Success", f"PDF downloaded to {file_path}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to download PDF: {e}")

# GUI Functions
def scrape_data():
    url = url_entry.get()
    data_type = data_type_var.get()
    num_items = num_items_entry.get() if num_items_entry.get().isdigit() else None

    if not url:
        messagebox.showerror("Error", "Please enter a URL or product name.")
        return

    # Disable the button to prevent multiple clicks
    scrape_button.config(state="disabled")

    # Clear previous results
    for widget in scrollable_frame.winfo_children():
        widget.destroy()

    # Show loading indicator
    loading_label = tk.Label(scrollable_frame, text="Scraping... Please wait...", font=("Arial", 14, "bold"), bg=scrollable_frame["bg"], fg="#003087")
    loading_label.pack(pady=10)
    progress_var.set(0)
    progress_bar.pack(pady=5)
    root.update()

    # Simulate scraping with a progress bar
    def update_progress():
        for i in range(1, 11):
            progress_var.set(i * 10)
            root.update()
            time.sleep(0.3)  # Slower progress for better visibility

    # Run the scraping in a separate thread
    def run_scraping(num_items_param):
        update_progress()  # Simulate progress while scraping

        if data_type == "Tables":
            tables = scrape_tables(url)
            progress_bar.pack_forget()
            loading_label.destroy()
            if tables:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                tk.Button(scrollable_frame, text="Export as CSV", command=lambda: export_tables_to_csv(tables), bg="green", fg="white").pack(pady=5)
                for i, table in enumerate(tables):
                    frame = tk.Frame(scrollable_frame, borderwidth=2, relief="groove", padx=10, pady=10, bg=scrollable_frame["bg"])
                    frame.pack(fill="x", pady=5)
                    fg_color = "#333333"
                    tk.Label(frame, text=f"Table {i + 1}", font=("Arial", 12, "bold"), bg=frame["bg"], fg=fg_color).pack(anchor="w")
                    text_area = scrolledtext.ScrolledText(frame, width=90, height=5)
                    text_area.pack(fill="x")
                    for row in table:
                        text_area.insert(tk.END, "\t".join(row) + "\n")
                    text_area.config(state="disabled")
                    tk.Button(frame, text="Copy Table", command=lambda t="\n".join("\t".join(row) for row in table): pyperclip.copy(t), bg="green", fg="white").pack(anchor="w", pady=2)
            else:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                fg_color = "#333333"
                tk.Label(scrollable_frame, text="No tables found.", font=("Arial", 12), bg=scrollable_frame["bg"], fg=fg_color).pack(pady=5)

        elif data_type == "Images":
            image_format = image_format_var.get()
            images = scrape_images(url, image_format)
            progress_bar.pack_forget()
            loading_label.destroy()
            if images:
                num_items = int(num_items_param) if num_items_param and int(num_items_param) <= len(images) else len(images)
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                tk.Button(scrollable_frame, text="Export as ZIP", command=lambda: export_images_to_zip(images[:num_items]), bg="green", fg="white").pack(pady=5)
                gallery_frame = tk.Frame(scrollable_frame, bg=scrollable_frame["bg"])
                gallery_frame.pack(fill="both", expand=True)
                for i, img_url in enumerate(images[:num_items], 1):
                    frame = tk.Frame(gallery_frame, borderwidth=2, relief="groove", padx=10, pady=10, bg=gallery_frame["bg"], width=700, height=100)
                    frame.pack(side="top", padx=5, pady=5, fill="x")
                    frame.pack_propagate(False)  # Prevent frame from resizing to fit contents
                    fg_color = "#333333"
                    tk.Label(frame, text=f"Image {i}", font=("Arial", 12, "bold"), bg=frame["bg"], fg=fg_color, anchor="w").pack(fill="x")
                    tk.Label(frame, text=f"URL: {img_url}", cursor="hand2", bg=frame["bg"], fg="blue", anchor="w", wraplength=650).pack(fill="x")
                    button_frame = tk.Frame(frame, bg=frame["bg"])
                    button_frame.pack(anchor="w", pady=2)
                    tk.Button(button_frame, text="Open", command=lambda u=img_url: webbrowser.open(u), bg="green", fg="white").pack(side="left", padx=5)
                    tk.Button(button_frame, text="Copy URL", command=lambda u=img_url: pyperclip.copy(u), bg="green", fg="white").pack(side="left", padx=5)
            else:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                fg_color = "#333333"
                tk.Label(scrollable_frame, text="No images found.", font=("Arial", 12), bg=scrollable_frame["bg"], fg=fg_color).pack(pady=5)

        elif data_type == "Movie Details":
            movie_data = scrape_movie_details(url)
            progress_bar.pack_forget()
            loading_label.destroy()
            if "error" in movie_data:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                fg_color = "#333333"
                tk.Label(scrollable_frame, text=movie_data["error"], font=("Arial", 12), bg=scrollable_frame["bg"], fg=fg_color).pack(pady=5)
            else:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                frame = tk.Frame(scrollable_frame, borderwidth=2, relief="groove", padx=10, pady=10, bg=scrollable_frame["bg"])
                frame.pack(fill="x", pady=5)
                details_frame = tk.Frame(frame, bg=frame["bg"])
                details_frame.pack(side="left", fill="x", expand=True)
                fg_color = "#333333"
                tk.Label(details_frame, text="Movie Details", font=("Arial", 12, "bold"), bg=details_frame["bg"], fg=fg_color).pack(anchor="w")
                tk.Label(details_frame, text=f"Name: {movie_data['name']}", bg=details_frame["bg"], fg=fg_color).pack(anchor="w")
                tk.Label(details_frame, text=f"Year: {movie_data['year']}", bg=buttons_frame["bg"], fg=fg_color).pack(anchor="w")
                tk.Label(details_frame, text=f"Rating: {movie_data['rating']}", bg=details_frame["bg"], fg=fg_color).pack(anchor="w")
                tk.Label(details_frame, text=f"Plot: {movie_data['plot']}", bg=details_frame["bg"], fg=fg_color).pack(anchor="w")
                tk.Label(details_frame, text=f"Genre: {movie_data['genre']}", bg=details_frame["bg"], fg=fg_color).pack(anchor="w")
                if movie_data["poster_url"] != "N/A":
                    tk.Label(details_frame, text=f"Poster URL: {movie_data['poster_url']}", cursor="hand2", bg=details_frame["bg"], fg="blue").pack(anchor="w")
                    tk.Button(details_frame, text="Open Poster", command=lambda u=movie_data['poster_url']: webbrowser.open(u), bg="green", fg="white").pack(anchor="w", pady=2)
                tk.Button(details_frame, text="Copy Details", command=lambda d=f"Name: {movie_data['name']}\nYear: {movie_data['year']}\nRating: {movie_data['rating']}\nPlot: {movie_data['plot']}\nGenre: {movie_data['genre']}": pyperclip.copy(d), bg="green", fg="white").pack(anchor="w", pady=2)

        elif data_type == "Videos":
            video_format = video_format_var.get()
            videos = scrape_videos(url, video_format)
            progress_bar.pack_forget()
            loading_label.destroy()
            if videos:
                num_items = int(num_items_param) if num_items_param and int(num_items_param) <= len(videos) else len(videos)
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                tk.Button(scrollable_frame, text="Export as ZIP", command=lambda: export_images_to_zip(videos[:num_items]), bg="green", fg="white").pack(pady=5)
                gallery_frame = tk.Frame(scrollable_frame, bg=scrollable_frame["bg"])
                gallery_frame.pack(fill="both", expand=True)
                for i, video_url in enumerate(videos[:num_items], 1):
                    frame = tk.Frame(gallery_frame, borderwidth=2, relief="groove", padx=10, pady=10, bg=gallery_frame["bg"], width=700, height=100)
                    frame.pack(side="top", padx=5, pady=5, fill="x")
                    frame.pack_propagate(False)  # Prevent frame from resizing to fit contents
                    fg_color = "#333333"
                    tk.Label(frame, text=f"Video {i}", font=("Arial", 12, "bold"), bg=frame["bg"], fg=fg_color, anchor="w").pack(fill="x")
                    tk.Label(frame, text=f"URL: {video_url}", cursor="hand2", bg=frame["bg"], fg="blue", anchor="w", wraplength=650).pack(fill="x")
                    button_frame = tk.Frame(frame, bg=frame["bg"])
                    button_frame.pack(anchor="w", pady=2)
                    tk.Button(button_frame, text="Play", command=lambda u=video_url: webbrowser.open(u), bg="green", fg="white").pack(side="left", padx=5)
                    tk.Button(button_frame, text="Copy URL", command=lambda u=video_url: pyperclip.copy(u), bg="green", fg="white").pack(side="left", padx=5)
            else:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                fg_color = "#333333"
                tk.Label(scrollable_frame, text="No videos found.", font=("Arial", 12), bg=scrollable_frame["bg"], fg=fg_color).pack(pady=5)

        elif data_type == "eBay Products":
            product_details = scrape_ebay_product(url)
            progress_bar.pack_forget()
            loading_label.destroy()
            if product_details:
                num_items = int(num_items_param) if num_items_param and int(num_items_param) <= len(product_details) else len(product_details)
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                for i, product in enumerate(product_details[:num_items], 1):
                    frame = tk.Frame(scrollable_frame, borderwidth=2, relief="groove", padx=10, pady=10, bg=scrollable_frame["bg"])
                    frame.pack(fill="x", pady=5)
                    try:
                        details_frame = tk.Frame(frame, bg=frame["bg"])
                        details_frame.pack(side="left", fill="x", expand=True)
                        fg_color = "#333333"
                        tk.Label(details_frame, text=f"Product {i}", font=("Arial", 12, "bold"), bg=details_frame["bg"], fg=fg_color).pack(anchor="w")
                        tk.Label(details_frame, text=f"Title: {product['title']}", bg=details_frame["bg"], fg=fg_color).pack(anchor="w")
                        tk.Label(details_frame, text=f"Price: {product['price']}", bg=details_frame["bg"], fg=fg_color).pack(anchor="w")
                        tk.Label(details_frame, text=f"Link: {product['link']}", cursor="hand2", bg=details_frame["bg"], fg="blue").pack(anchor="w")
                        tk.Button(details_frame, text="Open Link", command=lambda l=product['link']: webbrowser.open(l), bg="green", fg="white").pack(anchor="w", pady=2)
                        tk.Button(details_frame, text="Copy Link", command=lambda l=product['link']: pyperclip.copy(l), bg="green", fg="white").pack(anchor="w", pady=2)
                    except Exception as e:
                        logger.error(f"Error processing product {i}: {e}")
            else:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                fg_color = "#333333"
                tk.Label(scrollable_frame, text="No products found on eBay.", font=("Arial", 12), bg=scrollable_frame["bg"], fg=fg_color).pack(pady=5)

        elif data_type == "News Headlines":
            headlines = scrape_news_headlines(url)
            progress_bar.pack_forget()
            loading_label.destroy()
            if headlines:
                num_items = int(num_items_param) if num_items_param and int(num_items_param) <= len(headlines) else len(headlines)
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                for i, headline in enumerate(headlines[:num_items], 1):
                    frame = tk.Frame(scrollable_frame, borderwidth=2, relief="groove", padx=10, pady=10, bg=scrollable_frame["bg"])
                    frame.pack(fill="x", pady=5)
                    fg_color = "#333333"
                    tk.Label(frame, text=f"Headline {i}: {headline}", font=("Arial", 12), bg=frame["bg"], fg=fg_color).pack(anchor="w")
                    tk.Button(frame, text="Copy Headline", command=lambda h=headline: pyperclip.copy(h), bg="green", fg="white").pack(anchor="w", pady=2)
            else:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                fg_color = "#333333"
                tk.Label(scrollable_frame, text="No headlines found.", font=("Arial", 12), bg=scrollable_frame["bg"], fg=fg_color).pack(pady=5)

        elif data_type == "PDF Links":
            pdf_links = scrape_pdf_links(url)
            progress_bar.pack_forget()
            loading_label.destroy()
            if pdf_links:
                num_items = int(num_items_param) if num_items_param and int(num_items_param) <= len(pdf_links) else len(pdf_links)
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                for i, pdf in enumerate(pdf_links[:num_items], 1):
                    frame = tk.Frame(scrollable_frame, borderwidth=2, relief="groove", padx=10, pady=10, bg=scrollable_frame["bg"])
                    frame.pack(fill="x", pady=5)
                    fg_color = "#333333"
                    tk.Label(frame, text=f"PDF {i}: {pdf['name']}", font=("Arial", 12, "bold"), bg=frame["bg"], fg=fg_color).pack(anchor="w")
                    tk.Label(frame, text=f"URL: {pdf['url']}", cursor="hand2", bg=frame["bg"], fg="blue").pack(anchor="w")
                    tk.Button(frame, text="Extract Info", command=lambda p=pdf['url']: extract_pdf_info_callback(p), bg="green", fg="white").pack(side="left", padx=5, pady=2)
                    tk.Button(frame, text="Download PDF", command=lambda u=pdf['url'], n=pdf['name']: download_pdf(u, n), bg="green", fg="white").pack(side="left", padx=5, pady=2)
                    tk.Button(frame, text="Copy URL", command=lambda u=pdf['url']: pyperclip.copy(u), bg="green", fg="white").pack(side="left", padx=5, pady=2)
            else:
                for widget in scrollable_frame.winfo_children():
                    widget.destroy()
                fg_color = "#333333"
                tk.Label(scrollable_frame, text="No PDFs found.", font=("Arial", 12), bg=scrollable_frame["bg"], fg=fg_color).pack(pady=5)

        # Update history
        history_key = f"{url} - {data_type}"
        if history_key not in history and len(history) < 10:  # Limit to 10 recent searches
            history[history_key] = (url, data_type)
            history_combobox['values'] = ["Recent Searches"] + list(history.keys())
            history_combobox.set("Recent Searches")

        # Re-enable the button after scraping is done
        scrape_button.config(state="normal")

    # Start the scraping in a separate thread with num_items as an argument
    thread = threading.Thread(target=run_scraping, args=(num_items,))
    thread.start()

def extract_pdf_info_callback(pdf_url):
    info = extract_pdf_info(pdf_url)
    if info['success']:
        pdf_window = tk.Toplevel(root)
        pdf_window.title("PDF Information")
        pdf_window.geometry("600x400")
        text_area = scrolledtext.ScrolledText(pdf_window, width=70, height=20)
        text_area.pack(pady=10, padx=10)
        text_area.insert(tk.END, f"Title: {info['title']}\n")
        text_area.insert(tk.END, f"Author: {info['author']}\n")
        text_area.insert(tk.END, f"Page Count: {info['page_count']}\n")
        text_area.insert(tk.END, f"Text:\n{info['text']}\n")
        text_area.config(state="disabled")
        tk.Button(pdf_window, text="Copy Text", command=lambda t=info['text']: pyperclip.copy(t), bg="green", fg="white").pack(pady=5)
    else:
        messagebox.showerror("Error", info['error'])

def clear_results():
    for widget in scrollable_frame.winfo_children():
        widget.destroy()
    progress_bar.pack_forget()

def clear_entry(event):
    if url_entry.get() == "e.g., https://example.com or 'Harry Potter'":
        url_entry.delete(0, tk.END)

def load_history(event):
    selected = history_combobox.get()
    if selected and selected != "Recent Searches":
        url, data_type = history[selected]
        url_entry.delete(0, tk.END)
        url_entry.insert(0, url)
        data_type_var.set(data_type)

# GUI Setup
root = tk.Tk()
root.title("Web Scraper")
root.geometry("800x600")
root.configure(bg="#f5f5f5")

# Header Frame
header_frame = tk.Frame(root, bg="#003087", height=60)
header_frame.pack(fill="x")

# Logo/Title
logo_label = tk.Label(header_frame, text="Web Scraper", font=("Arial", 24, "bold"), fg="white", bg="#003087", padx=20)
logo_label.pack(side="left", pady=10)

# Footer Frame
footer_frame = tk.Frame(root, bg="#1a1a1a", height=30)
footer_frame.pack(side="bottom", fill="x")

# Copyright Text
copyright_label = tk.Label(footer_frame, text="© 2025 Web Scraper. All rights reserved.", font=("Arial", 10), fg="white", bg="#1a1a1a")
copyright_label.pack(side="left", padx=10, pady=5)

# Main Content Frame
content_frame = tk.Frame(root, bg="#ffffff", padx=20, pady=20, bd=2, relief="flat")
content_frame.pack(expand=True, fill="both", padx=10, pady=10)

# History Combobox
history = {}  # Initialize history dictionary
history_combobox = ttk.Combobox(root, width=50, state="readonly", font=("Arial", 12))
history_combobox['values'] = ["Recent Searches"]
history_combobox.set("Recent Searches")
history_combobox.bind("<<ComboboxSelected>>", load_history)
history_combobox.pack(pady=5)

# Input Frame
input_frame = tk.Frame(content_frame, bg="#ffffff")
input_frame.pack(pady=20)

# URL Input
tk.Label(input_frame, text="Enter URL or Name:", font=("Arial", 12), bg="#ffffff", fg="#333333").grid(row=0, column=0, padx=5, pady=5, sticky="e")
url_entry = tk.Entry(input_frame, width=50, font=("Arial", 12))
url_entry.grid(row=0, column=1, padx=5, pady=5)
url_entry.insert(0, "e.g., https://example.com or 'Harry Potter'")
url_entry.bind("<FocusIn>", clear_entry)

# Data Type Selection
tk.Label(input_frame, text="Select Data Type:", font=("Arial", 12), bg="#ffffff", fg="#333333").grid(row=1, column=0, padx=5, pady=5, sticky="e")
data_type_var = tk.StringVar(value="Tables")
data_types = ["Tables", "Images", "Movie Details", "Videos", "eBay Products", "News Headlines", "PDF Links"]
data_type_menu = ttk.Combobox(input_frame, textvariable=data_type_var, values=data_types, state="readonly", font=("Arial", 12))
data_type_menu.grid(row=1, column=1, padx=5, pady=5)

# Number of Items (Optional)
tk.Label(input_frame, text="Number of Items (optional):", font=("Arial", 12), bg="#ffffff", fg="#333333").grid(row=2, column=0, padx=5, pady=5, sticky="e")
num_items_entry = tk.Entry(input_frame, width=10, font=("Arial", 12))
num_items_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

# Image Format (for Images)
tk.Label(input_frame, text="Image Format (for Images):", font=("Arial", 12), bg="#ffffff", fg="#333333").grid(row=3, column=0, padx=5, pady=5, sticky="e")
image_format_var = tk.StringVar(value="all")
image_formats = ["all", "png", "jpg"]
image_format_menu = ttk.Combobox(input_frame, textvariable=image_format_var, values=image_formats, state="readonly", font=("Arial", 12))
image_format_menu.grid(row=3, column=1, padx=5, pady=5)

# Video Format (for Videos)
tk.Label(input_frame, text="Video Format (for Videos):", font=("Arial", 12), bg="#ffffff", fg="#333333").grid(row=4, column=0, padx=5, pady=5, sticky="e")
video_format_var = tk.StringVar(value="all")
video_formats = ["all", "mp4", "webm", "ogg"]
video_format_menu = ttk.Combobox(input_frame, textvariable=video_format_var, values=video_formats, state="readonly", font=("Arial", 12))
video_format_menu.grid(row=4, column=1, padx=5, pady=5)

# Buttons Frame
buttons_frame = tk.Frame(content_frame, bg="#ffffff")
buttons_frame.pack(pady=10)

# Scrape Button
scrape_button = tk.Button(buttons_frame, text="Scrape Now", command=scrape_data, font=("Arial", 12, "bold"), bg="#003087", fg="white", activebackground="#001f5f", padx=20, pady=5)
scrape_button.pack(side="left", padx=5)

# Clear Button
tk.Button(buttons_frame, text="Clear Results", command=clear_results, font=("Arial", 12), bg="#d32f2f", fg="white", activebackground="#b71c1c", padx=20, pady=5).pack(side="left", padx=5)

# Progress Bar
progress_var = tk.DoubleVar()
progress_bar = ttk.Progressbar(content_frame, variable=progress_var, maximum=100)
progress_bar.pack_forget()

# Result Frame with Scrollbar
result_frame = tk.Frame(content_frame, bg="#ffffff")
result_frame.pack(fill="both", expand=True, pady=10)

canvas = tk.Canvas(result_frame, bg="#ffffff")
scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=canvas.yview)
scrollable_frame = tk.Frame(canvas, bg="#ffffff")

scrollable_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)

canvas.configure(yscrollcommand=scrollbar.set)

def on_mouse_wheel(event):
    canvas.yview_scroll(-1 * (event.delta // 120), "units")

canvas.bind_all("<MouseWheel>", on_mouse_wheel)

scrollbar.pack(side="right", fill="y")
canvas.pack(side="left", fill="both", expand=True)
canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

# Start the GUI
root.mainloop()
import customtkinter as ctk
import requests
from bs4 import BeautifulSoup
import os
import zipfile
import io
from urllib.parse import urljoin, urlparse
import re
from PIL import Image, ImageTk
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Dict
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import logging
import platform

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

class WebScraperApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("Web Scraper")
        self.root.geometry("1200x800")
        
        self.image_data: Dict[str, bytes] = {}
        self.gallery_images: List[Tuple[ImageTk.PhotoImage, str, Tuple[int, int]]] = []
        self.all_image_urls: List[str] = []
        self.text_content: str = ""
        self.table_data: List[List[List[str]]] = []
        self.movie_details: Dict = {}
        self.book_details: Dict = {}
        self.video_urls: Tuple[str, ...] = ()
        self.ebay_products: List[Dict] = []
        self.news_headlines: Tuple[str, ...] = ()
        self.pdf_links: List[Dict] = []
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        self.image_formats = ["all", "png", "jpg", "webp", "gif"]
        self.video_formats = ["all", "mp4", "avi", "mkv", "mov", "webm"]
        
        self.setup_ui()
    
    def setup_ui(self):
        self.frame = ctk.CTkFrame(master=self.root)
        self.frame.pack(pady=20, padx=20, fill="both", expand=True)

        self.header_label = ctk.CTkLabel(master=self.frame, text="Web Scraper", font=("Helvetica", 24, "bold"))
        self.header_label.pack(pady=10)

        self.url_label = ctk.CTkLabel(master=self.frame, text="Enter URL or Search Term:", font=("Helvetica", 14))
        self.url_label.pack(pady=5)
        self.url_entry = ctk.CTkEntry(master=self.frame, placeholder_text="e.g., https://brainstation-23.com or movie/book name", width=600)
        self.url_entry.pack(pady=5)

        self.data_type_frame = ctk.CTkFrame(master=self.frame)
        self.data_type_frame.pack(pady=5)
        self.data_type_label = ctk.CTkLabel(master=self.data_type_frame, text="Select Data Type:", font=("Helvetica", 14))
        self.data_type_label.pack(side="left", padx=5)
        self.data_type_var = ctk.StringVar(value="Images")
        self.data_type_dropdown = ctk.CTkOptionMenu(master=self.data_type_frame, values=["Images", "Text", "Tables", "Movie Details", "Book Details", "Videos", "eBay Products", "News Headlines", "PDF Links"], variable=self.data_type_var, command=self.update_footer)
        self.data_type_dropdown.pack(side="left", padx=5)
        self.scrape_button = ctk.CTkButton(master=self.data_type_frame, text="Scrape Now", command=self.scrape_data, fg_color="#1e40af", hover_color="#1e3a8a")
        self.scrape_button.pack(side="left", padx=5)

        self.loading_label = ctk.CTkLabel(master=self.frame, text="", font=("Helvetica", 14))
        self.loading_label.pack(pady=5)
        self.result_label = ctk.CTkLabel(master=self.frame, text="", font=("Helvetica", 14))
        self.result_label.pack(pady=10)

        self.content_frame = ctk.CTkFrame(master=self.frame)
        self.content_frame.pack(fill="both", expand=True, pady=10)
        
        self.canvas = ctk.CTkCanvas(self.content_frame, bg="#ffffff")
        self.scrollbar = ctk.CTkScrollbar(self.content_frame, orientation="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.image_label = ctk.CTkLabel(self.content_frame, text="", width=200, height=300)
        self.text_box = ctk.CTkTextbox(self.content_frame, width=900, height=400, state="disabled")
        self.ebay_scrollable_frame = ctk.CTkScrollableFrame(self.content_frame, width=1100, height=400)
        
        self.filter_frame = ctk.CTkFrame(master=self.frame)
        self.filter_frame.pack(side="bottom", pady=10, fill="x")
        self.inner_filter_frame = ctk.CTkFrame(master=self.filter_frame)
        self.inner_filter_frame.pack(expand=True)

        self.num_tables_frame = ctk.CTkFrame(master=self.inner_filter_frame)
        self.num_tables_frame.pack(side="left", padx=5)
        self.num_tables_label = ctk.CTkLabel(master=self.num_tables_frame, text="Number of tables:", font=("Helvetica", 14))
        self.num_tables_label.pack(side="left", padx=5)
        self.num_tables_entry = ctk.CTkEntry(master=self.num_tables_frame, width=100, placeholder_text="All")
        self.num_tables_entry.pack(side="left", padx=5)

        self.num_items_frame = ctk.CTkFrame(master=self.inner_filter_frame)
        self.num_items_frame.pack(side="left", padx=5)
        self.num_items_label = ctk.CTkLabel(master=self.num_items_frame, text="Number of items:", font=("Helvetica", 14))
        self.num_items_label.pack(side="left", padx=5)
        self.num_items_entry = ctk.CTkEntry(master=self.num_items_frame, width=100, placeholder_text="All")
        self.num_items_entry.pack(side="left", padx=5)

        self.format_frame = ctk.CTkFrame(master=self.inner_filter_frame)
        self.format_frame.pack(side="left", padx=5)
        self.format_label = ctk.CTkLabel(master=self.format_frame, text="Format:", font=("Helvetica", 14))
        self.format_label.pack(side="left", padx=5)
        self.format_var = ctk.StringVar(value="all")
        self.format_dropdown = ctk.CTkOptionMenu(master=self.format_frame, values=self.image_formats, variable=self.format_var)
        self.format_dropdown.pack(side="left", padx=5)

        self.button_frame_bottom = ctk.CTkFrame(master=self.inner_filter_frame)
        self.button_frame_bottom.pack(side="left", padx=5)
        self.update_button = ctk.CTkButton(master=self.button_frame_bottom, text="Update Display", command=self.update_content, fg_color="#1e40af", hover_color="#1e3a8a")
        self.update_button.pack(side="left", padx=5)
        self.export_button = ctk.CTkButton(master=self.button_frame_bottom, text="Export", command=self.export_data, fg_color="#16a34a", hover_color="#15803d")
        self.export_button.pack(side="left", padx=5)

        self.mode_frame = ctk.CTkFrame(master=self.inner_filter_frame)
        self.mode_frame.pack(side="left", padx=5)
        self.dark_mode_button = ctk.CTkButton(master=self.mode_frame, text="Dark Mode", command=self.toggle_dark_mode)
        self.dark_mode_button.pack(side="left", padx=5)

        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.update_footer()

    def update_footer(self, *args):
        data_type = self.data_type_var.get()
        show_filters = data_type in ["Images", "Videos", "Tables", "eBay Products"]
        
        self.num_tables_frame.pack_forget()
        self.num_items_frame.pack_forget()
        self.format_frame.pack_forget()
        self.button_frame_bottom.pack_forget()
        self.mode_frame.pack_forget()
        
        if show_filters:
            if data_type == "Tables":
                self.num_tables_frame.pack(side="left", padx=5)
            if data_type in ["Images", "Videos", "eBay Products"]:
                self.num_items_frame.pack(side="left", padx=5)
                self.format_frame.pack(side="left", padx=5)
                if data_type in ["Images", "eBay Products"]:
                    self.format_dropdown.configure(values=self.image_formats)
                    if self.format_var.get() not in self.image_formats:
                        self.format_var.set("all")
                elif data_type == "Videos":
                    self.format_dropdown.configure(values=self.video_formats)
                    if self.format_var.get() not in self.video_formats:
                        self.format_var.set("all")
        self.button_frame_bottom.pack(side="left", padx=5)
        self.mode_frame.pack(side="left", padx=5)
        
        self.inner_filter_frame.pack(expand=True)
        self.filter_frame.pack(side="bottom", pady=10, fill="x")

    def is_valid_url(self, url: str) -> bool:
        return bool(re.match(r'^https?://[^\s/$.?#].[^\s]*$', url))

    def scrape_data(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            self.result_label.configure(text="Please enter a URL or search term!", text_color="red")
            return
        if self.data_type_var.get() in ["Movie Details", "Book Details"] and not url.replace(" ", "").isalnum():
            self.result_label.configure(text="Please enter a valid movie or book name!", text_color="red")
            return
        if not self.is_valid_url(url) and self.data_type_var.get() not in ["Movie Details", "Book Details", "eBay Products"]:
            url = "https://" + url if not url.startswith(("http://", "https://")) else url
            if not self.is_valid_url(url):
                self.result_label.configure(text="Invalid URL format!", text_color="red")
                return
        
        self.show_loading(True)
        threading.Thread(target=lambda: self.perform_scrape(url), daemon=True).start()

    def perform_scrape(self, url: str) -> None:
        self.image_data.clear()
        self.gallery_images.clear()
        self.all_image_urls.clear()
        self.text_content = ""
        self.table_data.clear()
        self.movie_details.clear()
        self.book_details.clear()
        self.video_urls = ()
        self.ebay_products.clear()
        self.news_headlines = ()
        self.pdf_links.clear()

        data_type = self.data_type_var.get()
        try:
            if data_type == "Images":
                self.result_label.configure(text="Scraping images...")
                self.all_image_urls = self.scrape_images(url, self.format_var.get()) or []
                if not self.all_image_urls:
                    self.result_label.configure(text="No images found!", text_color="red")
                else:
                    self.update_content()
            elif data_type == "Text":
                self.result_label.configure(text="Scraping text...")
                response = requests.get(url, headers=self.headers, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                self.text_content = soup.get_text(separator="\n", strip=True)
                if not self.text_content:
                    self.result_label.configure(text="No text found!", text_color="red")
                else:
                    self.update_content()
            elif data_type == "Tables":
                self.result_label.configure(text="Scraping tables...")
                self.table_data = self.scrape_tables(url) or []
                if not self.table_data:
                    self.result_label.configure(text="No tables found!", text_color="red")
                else:
                    self.update_content()
            elif data_type == "Movie Details":
                self.result_label.configure(text="Scraping movie details...")
                self.movie_details = self.scrape_movie_details(url) or {"error": "No data found!"}
                self.update_content()
            elif data_type == "Book Details":
                self.result_label.configure(text="Scraping book details...")
                self.book_details = self.scrape_book_details(url) or {"error": "No data found!"}
                self.update_content()
            elif data_type == "Videos":
                self.result_label.configure(text="Scraping videos...")
                self.video_urls = self.scrape_videos(url, self.format_var.get()) or ()
                if not self.video_urls:
                    self.result_label.configure(text="No videos found!", text_color="red")
                else:
                    self.update_content()
            elif data_type == "eBay Products":
                self.result_label.configure(text="Scraping eBay products...")
                self.ebay_products = self.scrape_ebay_product(url) or []
                if not self.ebay_products:
                    self.result_label.configure(text="No eBay products found!", text_color="red")
                else:
                    self.update_content()
            elif data_type == "News Headlines":
                self.result_label.configure(text="Scraping news headlines...")
                self.news_headlines = self.scrape_news_headlines(url) or ()
                if not self.news_headlines:
                    self.result_label.configure(text="No news headlines found!", text_color="red")
                else:
                    self.update_content()
            elif data_type == "PDF Links":
                self.result_label.configure(text="Scraping PDF links...")
                self.pdf_links = self.scrape_pdf_links(url) or []
                if not self.pdf_links:
                    self.result_label.configure(text="No PDF links found!", text_color="red")
                else:
                    self.update_content()
        except Exception as e:
            self.result_label.configure(text=f"Failed to scrape: {str(e)}", text_color="red")
        finally:
            self.show_loading(False)

    def scrape_tables(self, url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            tables = soup.find_all('table')
            table_data = []
            for table in tables:
                headers = table.find_all('th')
                header_row = [header.text.strip() for header in headers] if headers else []
                rows = table.find_all('tr')
                table_rows = []
                start_idx = 1 if header_row else 0
                for row in rows[start_idx:]:
                    cols = row.find_all('td')
                    if cols:
                        table_rows.append([col.text.strip() for col in cols])
                if header_row:
                    table_rows.insert(0, header_row)
                if table_rows:
                    table_data.append(table_rows)
            return table_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def scrape_images(self, url, image_format):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            images = soup.find_all(['img', 'image'])
            image_urls = []
            for img in images:
                img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if img_url:
                    full_url = urljoin(url, img_url)
                    image_urls.append(full_url)
            if not image_urls:
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
                    if img_url:
                        full_url = urljoin(url, img_url)
                        image_urls.append(full_url)
                driver.quit()
            return image_urls if image_urls else None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def scrape_movie_details(self, movie_name):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        try:
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
            title_elem = soup.select_one('h1')
            title = title_elem.text.strip() if title_elem else "N/A"
            poster_elem = soup.select_one('img.ipc-image')
            poster_url = poster_elem.get('src', "N/A") if poster_elem else "N/A"
            year_elem = soup.select_one('a[href*="/releaseinfo"]')
            year = year_elem.text.strip() if year_elem else "N/A"
            rating_elem = soup.select_one('div[data-testid="hero-rating-bar__aggregate-rating__score"] span')
            rating = f"{rating_elem.text.strip()}/10" if rating_elem else "N/A"
            plot_elem = soup.select_one('span[data-testid="plot-xl"]')
            plot = plot_elem.text.strip() if plot_elem else "N/A"
            genre_elems = soup.select('.ipc-chip__text')
            genres = [genre.text.strip() for genre in genre_elems] if genre_elems else ["N/A"]
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

    def scrape_book_details(self, book_name):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124"}
        try:
            search_url = f"https://openlibrary.org/search?q={book_name.replace(' ', '+')}&mode=everything"
            search_response = requests.get(search_url, headers=headers, timeout=10)
            search_response.raise_for_status()
            search_soup = BeautifulSoup(search_response.content, 'html.parser')
            first_result = search_soup.select_one('li.searchResultItem')
            if not first_result:
                return {"error": "No book found with that name."}
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
            book_link = first_result.select_one('h3.booktitle a')['href']
            detail_url = f"https://openlibrary.org{book_link}"
            detail_response = requests.get(detail_url, headers=headers, timeout=10)
            detail_response.raise_for_status()
            detail_soup = BeautifulSoup(detail_response.content, 'html.parser')
            description_elem = detail_soup.select_one('div.read-more__content')
            description = " ".join([p.text.strip() for p in description_elem.find_all('p') if not p.find('a')]) if description_elem else "N/A"
            return {
                "name": title,
                "cover_url": cover_url,
                "author": author,
                "year": year,
                "rating": rating,
                "description": description,
                "book_link": detail_url
            }
        except requests.exceptions.RequestException as e:
            return {"error": f"Network error: {e}"}
        except Exception as e:
            return {"error": f"An error occurred: {e}"}

    def scrape_videos(self, url, video_format):
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            videos = soup.find_all('video')
            video_urls = []
            for video in videos:
                video_sources = video.find_all('source')
                for source in video_sources:
                    video_url = source.get('src')
                    if video_url:
                        parsed_url = urlparse(video_url)
                        clean_url = parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path
                        extension = os.path.splitext(clean_url)[1].lower()
                        extension = extension[1:] if extension else ""
                        if video_format != 'all' and extension != video_format.lower():
                            continue
                        if not video_url.startswith(('http://', 'https://')):
                            video_url = urljoin(url, video_url)
                        video_urls.append(video_url)
            if not video_urls:
                logger.info(f"No videos found with BS4 at {url}, trying Selenium")
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                driver.get(url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "video")))
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                videos = soup.find_all('video')
                for video in videos:
                    video_sources = video.find_all('source')
                    for source in video_sources:
                        video_url = source.get('src')
                        if video_url:
                            parsed_url = urlparse(video_url)
                            clean_url = parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path
                            extension = os.path.splitext(clean_url)[1].lower()
                            extension = extension[1:] if extension else ""
                            if video_format != 'all' and extension != video_format.lower():
                                continue
                            if not video_url.startswith(('http://', 'https://')):
                                video_url = urljoin(url, video_url)
                            video_urls.append(video_url)
                driver.quit()
            return tuple(video_urls) if video_urls else ()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error in scrape_videos: {e}")
            return None

    def scrape_ebay_product(self, product_name):
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
                product_listings = soup.select('li[data-viewport]')

            allowed_formats = {
                'png': ['.png'],
                'jpg': ['.jpg', '.jpeg'],
                'webp': ['.webp'],
                'gif': ['.gif'],
                'all': ['.png', '.jpg', '.jpeg', '.webp', '.gif']
            }
            selected_format = self.format_var.get()

            for product in product_listings[2:]:
                try:
                    title_elem = product.select_one('.s-item__title')
                    title = title_elem.text.strip() if title_elem else "N/A"
                    link_elem = product.select_one('a.s-item__link')
                    link = link_elem['href'] if link_elem else "N/A"
                    image_elem = product.select_one('img')
                    image_url = image_elem.get('src') if image_elem else None
                    if image_url:
                        if any(image_url.lower().endswith(ext) for ext in allowed_formats[selected_format]):
                            full_image_url = image_url
                        else:
                            full_image_url = "N/A"
                    else:
                        full_image_url = "N/A"
                    price_elem = product.select_one('.s-item__price')
                    price = price_elem.text.strip() if price_elem else "N/A"
                    rating_elem = product.select_one('.s-item__reviews')
                    rating = rating_elem.text.strip() if rating_elem else "N/A"
                    if title != "N/A" and link != "N/A":
                        product_details.append({
                            "title": title,
                            "link": link,
                            "image_url": full_image_url,
                            "price": price,
                            "rating": rating
                        })
                except AttributeError as e:
                    logger.error(f"Error parsing product: {e}")
                    continue
            return product_details if product_details else None
        except Exception as e:
            logger.error(f"Error fetching eBay with Selenium: {e}")
            return None
        finally:
            driver.quit()

    def scrape_news_headlines(self, url):
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

    def scrape_pdf_links(self, url):
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

    def download_image(self, img_url: str) -> Tuple[str, bytes]:
        try:
            img_response = requests.get(img_url, headers=self.headers, timeout=5)
            img_response.raise_for_status()
            return img_url, img_response.content
        except Exception:
            return img_url, None

    def update_content(self) -> None:
        data_type = self.data_type_var.get()
        self.canvas.pack_forget()
        self.scrollbar.pack_forget()
        self.image_label.pack_forget()
        self.text_box.pack_forget()
        self.ebay_scrollable_frame.pack_forget()
        
        if data_type == "Images":
            self.update_image_list()
        elif data_type == "Text":
            self.update_text_display()
        elif data_type == "Tables":
            self.update_table_display()
        elif data_type == "Movie Details":
            self.update_movie_display()
        elif data_type == "Book Details":
            self.update_book_display()
        elif data_type == "Videos":
            self.update_video_display()
        elif data_type == "eBay Products":
            self.update_ebay_display()
        elif data_type == "News Headlines":
            self.update_news_display()
        elif data_type == "PDF Links":
            self.update_pdf_display()
        self.update_footer()

    def update_image_list(self) -> None:
        self.image_data.clear()
        self.gallery_images.clear()
        
        # Define allowed formats based on current self.format_var
        allowed_formats = {
            'png': ['.png'],
            'jpg': ['.jpg', '.jpeg'],
            'webp': ['.webp'],
            'gif': ['.gif'],
            'all': ['.png', '.jpg', '.jpeg', '.webp', '.gif']
        }
        selected_format = self.format_var.get()
        
        # Filter images by format from self.all_image_urls
        filtered_urls = [
            url for url in self.all_image_urls
            if any(url.lower().endswith(ext) for ext in allowed_formats[selected_format])
        ]
        
        # Apply number of items filter
        num_items = self.num_items_entry.get().strip()
        num_items = int(num_items) if num_items.isdigit() and int(num_items) > 0 else len(filtered_urls)
        filtered_urls = filtered_urls[:min(num_items, len(filtered_urls))]
        
        if not filtered_urls:
            self.result_label.configure(text="No images match the updated criteria!", text_color="red")
            self.root.after(0, self.update_gallery)
            return
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(self.download_image, filtered_urls))
        
        for img_url, content in results:
            if content:
                self.image_data[img_url] = content
                img = Image.open(io.BytesIO(content))
                img.thumbnail((400, 400), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.gallery_images.append((photo, img_url, img.size))
        
        self.root.after(0, self.update_gallery)

    def update_gallery(self) -> None:
        self.text_box.pack_forget()
        self.image_label.pack_forget()
        self.ebay_scrollable_frame.pack_forget()
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas.delete("all")
        if not self.gallery_images:
            self.result_label.configure(text="No images match the criteria!", text_color="red")
            return
        
        canvas_width = self.canvas.winfo_width() or 1100
        img_width = 400  # Actual image width
        spacing = 20    # Spacing between images
        img_width_with_spacing = img_width + spacing
        
        # Calculate the number of columns based on canvas width
        num_columns = max(1, canvas_width // img_width_with_spacing)
        
        # Total number of images
        num_images = len(self.gallery_images)
        num_rows = (num_images + num_columns - 1) // num_columns  # Ceiling division for rows
        
        y = 20
        for row in range(num_rows):
            start_idx = row * num_columns
            end_idx = min(start_idx + num_columns, num_images)
            images_in_row = end_idx - start_idx
            
            # Calculate the total width of the row (including spacing)
            row_width = images_in_row * img_width_with_spacing - spacing  # Subtract extra spacing at the end
            start_x = (canvas_width - row_width) // 2  # Center the row
            
            x = start_x
            for i in range(start_idx, end_idx):
                photo, img_url, original_size = self.gallery_images[i]
                img_label = ctk.CTkLabel(self.canvas, image=photo, text="", cursor="hand2")
                img_label.image = photo
                img_label.bind("<Button-1>", lambda e, url=img_url: self.show_image_in_popup(url))
                self.canvas.create_window(x, y, anchor="nw", window=img_label)
                x += img_width_with_spacing
            
            y += max(220, original_size[1] + 20)  # Use the tallest image height + spacing
        
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.result_label.configure(text=f"Found {len(self.gallery_images)} images", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def update_text_display(self) -> None:
        self.text_box.pack(fill="both", expand=True)
        
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", self.text_content)
        self.text_box.configure(state="disabled")
        self.result_label.configure(text=f"Text scraped ({len(self.text_content)} characters)", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def update_table_display(self) -> None:
        self.text_box.pack(fill="both", expand=True)
        
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        
        if not self.table_data:
            self.result_label.configure(text="No tables to display!", text_color="red")
            return
        
        num_tables = self.num_tables_entry.get().strip()
        num_tables = int(num_tables) if num_tables.isdigit() and int(num_tables) > 0 else len(self.table_data)
        filtered_tables = self.table_data[:min(num_tables, len(self.table_data))]
        
        for table_idx, table in enumerate(filtered_tables, 1):
            self.text_box.insert("end", f"Table #{table_idx}:\n")
            for row in table:
                self.text_box.insert("end", "\t".join(row) + "\n")
            self.text_box.insert("end", "\n")
        
        self.text_box.configure(state="disabled")
        self.result_label.configure(text=f"Found {len(self.table_data)} tables (Displaying {len(filtered_tables)})", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def update_movie_display(self) -> None:
        self.image_label.pack_forget()
        self.text_box.pack_forget()
        
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.image_label.configure(image=None)
        
        if "error" in self.movie_details:
            self.text_box.insert("end", self.movie_details["error"])
            self.text_box.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        else:
            if self.movie_details.get("poster_url", "N/A") != "N/A":
                try:
                    img_response = requests.get(self.movie_details["poster_url"], headers=self.headers, timeout=5)
                    img_response.raise_for_status()
                    img = Image.open(io.BytesIO(img_response.content))
                    img.thumbnail((200, 300), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.image_label.configure(image=photo)
                    self.image_label.image = photo
                    self.image_label.pack(side="left", padx=10, pady=10, fill="y")
                except Exception as e:
                    self.text_box.insert("end", f"Failed to load poster: {str(e)}\n\n")
            
            for key, value in self.movie_details.items():
                if key != "poster_url":
                    self.text_box.insert("end", f"{key.capitalize()}: {value}\n")
            self.text_box.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        self.text_box.configure(state="disabled")
        self.result_label.configure(text="Movie details scraped", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def update_book_display(self) -> None:
        self.image_label.pack_forget()
        self.text_box.pack_forget()
        
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.image_label.configure(image=None)
        
        if "error" in self.book_details:
            self.text_box.insert("end", self.book_details["error"])
            self.text_box.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        else:
            if self.book_details.get("cover_url", "N/A") != "N/A":
                try:
                    img_response = requests.get(self.book_details["cover_url"], headers=self.headers, timeout=5)
                    img_response.raise_for_status()
                    img = Image.open(io.BytesIO(img_response.content))
                    img.thumbnail((200, 300), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.image_label.configure(image=photo)
                    self.image_label.image = photo
                    self.image_label.pack(side="left", padx=10, pady=10, fill="y")
                except Exception as e:
                    self.text_box.insert("end", f"Failed to load cover: {str(e)}\n\n")
            
            for key, value in self.book_details.items():
                if key != "cover_url":
                    self.text_box.insert("end", f"{key.capitalize()}: {value}\n")
            self.text_box.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        self.text_box.configure(state="disabled")
        self.result_label.configure(text="Book details scraped", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def update_video_display(self) -> None:
        self.text_box.pack(fill="both", expand=True)
        
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        num_items = self.num_items_entry.get().strip()
        num_items = int(num_items) if num_items.isdigit() and int(num_items) > 0 else len(self.video_urls)
        video_urls_to_display = list(self.video_urls)[:num_items]
        for i, video_url in enumerate(video_urls_to_display, 1):
            self.text_box.insert("end", f"Video {i}: {video_url}\n")
        self.text_box.configure(state="disabled")
        self.result_label.configure(text=f"Found {len(self.video_urls)} videos (Displaying {len(video_urls_to_display)})", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def update_ebay_display(self) -> None:
        self.ebay_scrollable_frame.pack(fill="both", expand=True)
        
        # Clear previous content
        for widget in self.ebay_scrollable_frame.winfo_children():
            widget.destroy()
        
        if not self.ebay_products:
            error_label = ctk.CTkLabel(self.ebay_scrollable_frame, text="No eBay products to display!", font=("Helvetica", 14))
            error_label.pack(pady=10)
            self.result_label.configure(text="No eBay products found!", text_color="red")
            return
        
        for i, product in enumerate(self.ebay_products, 1):
            # Create a frame for each product
            product_frame = ctk.CTkFrame(self.ebay_scrollable_frame)
            product_frame.pack(fill="x", padx=10, pady=10)
            
            # Image
            image_url = product.get("image_url", "N/A")
            if image_url != "N/A" and "placeholder" not in image_url.lower():  # Skip placeholders
                try:
                    img_response = requests.get(image_url, headers=self.headers, timeout=5)
                    img_response.raise_for_status()
                    img = Image.open(io.BytesIO(img_response.content))
                    img.thumbnail((150, 150), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    img_label = ctk.CTkLabel(product_frame, image=photo, text="")
                    img_label.image = photo  # Keep reference
                    img_label.pack(side="left", padx=10, pady=10)
                except Exception as e:
                    error_label = ctk.CTkLabel(product_frame, text=f"Failed to load image: {str(e)}", font=("Helvetica", 12))
                    error_label.pack(side="left", padx=10, pady=10)
            else:
                no_img_label = ctk.CTkLabel(product_frame, text="No image available", font=("Helvetica", 12))
                no_img_label.pack(side="left", padx=10, pady=10)
            
            # Details
            details_text = f"Product {i}:\n"
            for key, value in product.items():
                if key != "image_url":  # Skip image_url since it’s displayed
                    details_text += f"  {key.capitalize()}: {value}\n"
            details_label = ctk.CTkLabel(product_frame, text=details_text, font=("Helvetica", 12), justify="left", wraplength=900)
            details_label.pack(side="left", padx=10, pady=10)
        
        self.result_label.configure(text=f"Found {len(self.ebay_products)} eBay products", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def update_news_display(self) -> None:
        self.text_box.pack(fill="both", expand=True)
        
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        for i, headline in enumerate(self.news_headlines, 1):
            self.text_box.insert("end", f"Headline {i}: {headline}\n")
        self.text_box.configure(state="disabled")
        self.result_label.configure(text=f"Found {len(self.news_headlines)} news headlines", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def update_pdf_display(self) -> None:
        self.text_box.pack(fill="both", expand=True)
        
        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        for i, pdf in enumerate(self.pdf_links, 1):
            self.text_box.insert("end", f"PDF {i}:\n")
            for key, value in pdf.items():
                self.text_box.insert("end", f"  {key.capitalize()}: {value}\n")
            self.text_box.insert("end", "\n")
        self.text_box.configure(state="disabled")
        self.result_label.configure(text=f"Found {len(self.pdf_links)} PDF links", text_color="black" if ctk.get_appearance_mode() == "Light" else "white")

    def show_image_in_popup(self, url: str) -> None:
        popup = ctk.CTkToplevel(self.root)
        popup.title("Image Viewer")
        popup.geometry("800x600")
        popup.transient(self.root)
        popup.grab_set()
        
        canvas_popup = ctk.CTkCanvas(popup, bg="#ffffff", width=780, height=520)
        scrollbar_x = ctk.CTkScrollbar(popup, orientation="horizontal", command=canvas_popup.xview)
        scrollbar_y = ctk.CTkScrollbar(popup, orientation="vertical", command=canvas_popup.yview)
        canvas_popup.configure(xscrollcommand=scrollbar_x.set, yscrollcommand=scrollbar_y.set)
        
        try:
            img = Image.open(io.BytesIO(self.image_data[url]))
            img.thumbnail((780, 520), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            x_pos = (780 - img.width) // 2
            y_pos = (520 - img.height) // 2
            canvas_popup.create_image(x_pos, y_pos, anchor="nw", image=photo)
            canvas_popup.image = photo
            canvas_popup.config(scrollregion=(0, 0, img.width, img.height))
            
            canvas_popup.pack(side="top", fill="both", expand=True)
            scrollbar_y.pack(side="right", fill="y")
            scrollbar_x.pack(side="bottom", fill="x")
            
            button_frame = ctk.CTkFrame(popup)
            button_frame.pack(side="bottom", pady=10)
            
            index = len(self.image_data)
            filename = f"image_{index:02d}.jpg"
            def save_image():
                try:
                    with open(filename, "wb") as f:
                        f.write(self.image_data[url])
                    self.result_label.configure(text=f"Image saved as '{filename}'!", text_color="green")
                except Exception as e:
                    self.result_label.configure(text=f"Failed to save: {str(e)}", text_color="red")
                popup.destroy()
            
            download_button = ctk.CTkButton(button_frame, text="Download", command=save_image, fg_color="#16a34a", hover_color="#15803d")
            download_button.pack(side="left", padx=5)
            close_button = ctk.CTkButton(button_frame, text="Close", command=popup.destroy)
            close_button.pack(side="left", padx=5)
            
            popup.update_idletasks()
            x = (popup.winfo_screenwidth() // 2) - 400
            y = (popup.winfo_screenheight() // 2) - 300
            popup.geometry(f"800x600+{x}+{y}")
        except Exception as e:
            error_label = ctk.CTkLabel(popup, text=f"Failed to load image: {str(e)}", font=("Helvetica", 14))
            error_label.pack(pady=10)
            close_button = ctk.CTkButton(popup, text="Close", command=popup.destroy)
            close_button.pack(pady=10)

    def export_data(self) -> None:
        data_type = self.data_type_var.get()
        if data_type == "Images" and not self.image_data:
            self.result_label.configure(text="No images to export!", text_color="red")
            return
        if data_type == "Text" and not self.text_content:
            self.result_label.configure(text="No text to export!", text_color="red")
            return
        if data_type == "Tables" and not self.table_data:
            self.result_label.configure(text="No tables to export!", text_color="red")
            return
        if data_type == "Movie Details" and not self.movie_details:
            self.result_label.configure(text="No movie details to export!", text_color="red")
            return
        if data_type == "Book Details" and not self.book_details:
            self.result_label.configure(text="No book details to export!", text_color="red")
            return
        if data_type == "Videos" and not self.video_urls:
            self.result_label.configure(text="No videos to export!", text_color="red")
            return
        if data_type == "eBay Products" and not self.ebay_products:
            self.result_label.configure(text="No eBay products to export!", text_color="red")
            return
        if data_type == "News Headlines" and not self.news_headlines:
            self.result_label.configure(text="No news headlines to export!", text_color="red")
            return
        if data_type == "PDF Links" and not self.pdf_links:
            self.result_label.configure(text="No PDF links to export!", text_color="red")
            return
        
        self.show_loading(True)
        threading.Thread(target=self.perform_export, daemon=True).start()

    def perform_export(self) -> None:
        try:
            data_type = self.data_type_var.get()
            if data_type == "Images":
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for i, (url, data) in enumerate(self.image_data.items()):
                        ext = url.split('.')[-1].split('?')[0] or 'jpg'
                        zip_file.writestr(f"image_{i+1:02d}.{ext}", data)
                zip_buffer.seek(0)
                filename = "images.zip"
                with open(filename, "wb") as f:
                    f.write(zip_buffer.getvalue())
            elif data_type == "Text":
                filename = "text.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(self.text_content)
            elif data_type == "Tables":
                filename = "tables.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    for i, table in enumerate(self.table_data, 1):
                        f.write(f"Table {i}:\n")
                        for row in table:
                            f.write("\t".join(row) + "\n")
                        f.write("\n")
            elif data_type == "Movie Details":
                filename = "movie_details.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    for key, value in self.movie_details.items():
                        f.write(f"{key.capitalize()}: {value}\n")
            elif data_type == "Book Details":
                filename = "book_details.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    for key, value in self.book_details.items():
                        f.write(f"{key.capitalize()}: {value}\n")
            elif data_type == "Videos":
                filename = "videos.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    for i, video_url in enumerate(self.video_urls, 1):
                        f.write(f"Video {i}: {video_url}\n")
            elif data_type == "eBay Products":
                filename = "ebay_products.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    for i, product in enumerate(self.ebay_products, 1):
                        f.write(f"Product {i}:\n")
                        for key, value in product.items():
                            f.write(f"  {key.capitalize()}: {value}\n")
                        f.write("\n")
            elif data_type == "News Headlines":
                filename = "news_headlines.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    for i, headline in enumerate(self.news_headlines, 1):
                        f.write(f"Headline {i}: {headline}\n")
            elif data_type == "PDF Links":
                filename = "pdf_links.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    for i, pdf in enumerate(self.pdf_links, 1):
                        f.write(f"PDF {i}:\n")
                        for key, value in pdf.items():
                            f.write(f"  {key.capitalize()}: {value}\n")
                        f.write("\n")
            
            self.root.after(0, lambda: [
                self.show_loading(False),
                self.result_label.configure(text=f"Exported as '{filename}'!", text_color="green"),
                self.open_file(filename)
            ])
        except Exception as e:
            self.root.after(0, lambda: [
                self.show_loading(False),
                self.result_label.configure(text=f"Export failed: {str(e)}", text_color="red")
            ])

    def open_file(self, filename: str) -> None:
        if platform.system() == "Windows":
            os.startfile(filename)
        elif platform.system() == "Darwin":
            os.system(f"open {filename}")
        else:
            os.system(f"xdg-open {filename}")

    def show_loading(self, state: bool = True) -> None:
        self.loading_label.configure(text="Processing..." if state else "")
        self.root.update()

    def toggle_dark_mode(self) -> None:
        new_mode = "dark" if ctk.get_appearance_mode() == "Light" else "light"
        ctk.set_appearance_mode(new_mode)
        self.dark_mode_button.configure(text="Light Mode" if new_mode == "dark" else "Dark Mode")
        self.result_label.configure(text_color="black" if new_mode == "light" else "white")
        self.update_content()

    def on_canvas_resize(self, event) -> None:
        if self.data_type_var.get() == "Images":
            self.update_gallery()

if __name__ == "__main__":
    root = ctk.CTk()
    app = WebScraperApp(root)
    root.mainloop()
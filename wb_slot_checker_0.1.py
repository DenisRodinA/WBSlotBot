import os
import sys
import time
import datetime

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementClickInterceptedException, 
    StaleElementReferenceException, WebDriverException, NoSuchElementException
)

def get_local_user_data_path():
    # Получаем директорию, в которой находится сам скрипт
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    profile_path = os.path.join(script_dir, "MySeleniumProfile")
    
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Папка профиля Chrome не найдена: {profile_path}")
    
    return profile_path

def get_dates_by_weekdays(input_str, num_days=30):
    days_map = {
        "пн": 0, "вт": 1, "ср": 2, "чт": 3,
        "пт": 4, "сб": 5, "вс": 6
    }

    weekdays_reverse = {v: k for k, v in days_map.items()}  # Чтобы получить день недели по номеру

    months = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }

    selected_days = [
        days_map[day.strip().lower()]
        for day in input_str.split(",")
        if day.strip().lower() in days_map
    ]

    if not selected_days:
        print("❌ Не удалось распознать ни один день недели.")
        return []

    today = datetime.date.today()
    result = []

    for i in range(1, num_days + 1):
        date = today + datetime.timedelta(days=i)
        if date.weekday() in selected_days:
            day_num = date.day
            month_str = months[date.month]
            weekday_str = weekdays_reverse[date.weekday()]
            # Формируем строку в формате '26 июня, чт'
            formatted_date = f"{day_num} {month_str}, {weekday_str}"
            result.append(formatted_date)

    return result


class WBOrderFinder:
    def __init__(self, order_number, user_data_dir, profile_directory, driver_path, dates_list):
        self.order_number = order_number.strip()
        self.options = Options()

        # Настройки профиля Chrome, чтобы не заходить каждый раз вручную
        self.options.add_argument(f"--user-data-dir={user_data_dir}")
        self.options.add_argument(f"--profile-directory={profile_directory}")

        # Максимальный размер окна, отключение детектирования автоматизации
        self.options.add_argument("--start-maximized")
        self.options.add_argument("--disable-blink-features=AutomationControlled")

        # Чтобы окно браузера не закрывалось сразу после завершения скрипта
        self.options.add_experimental_option("detach", True)

        try:
            print(f"🚀 Запускаем Chrome с профилем: {profile_directory}")
            service = Service(driver_path)
            self.driver = webdriver.Chrome(service=service, options=self.options)
        except WebDriverException as e:
            print(f"❌ Ошибка запуска WebDriver: {e}")
            self.driver = None

        self.dates_list = dates_list    

    def open_page(self, url):
        """Открываем страницу и проверяем авторизацию."""
        if not self.driver:
            print("🚫 Драйвер не инициализирован, пропускаем открытие страницы.")
            return False

        print(f"➡️ Переход на страницу: {url}")
        self.driver.get(url)
        time.sleep(3)  # Ждём загрузку

        # Проверяем, не на странице ли авторизации
        if any(x in self.driver.current_url for x in ["login", "signin", "auth"]):
            print("🔐 Необходима авторизация. Войдите вручную.")
            input("⏸️ Нажмите Enter после входа...")
            self.driver.get(url)
            time.sleep(3)

            if any(x in self.driver.current_url for x in ["login", "signin", "auth"]):
                print("🚫 Не удалось авторизоваться. Завершаем.")
                self.cleanup()
                return False
        return True

    def find_order_row(self):
        """Ищем строку с заказом в таблице."""
        if not self.driver:
            print("🚫 Драйвер не инициализирован, пропускаем поиск заказа.")
            return False

        try:
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//table"))
            )
        except TimeoutException:
            print("❌ Таблица с заказами не загрузилась.")
            return False

        print(f"🔎 Ищем заказ: {self.order_number}")

        scroll_attempts = 0
        while scroll_attempts < 10:
            rows = self.driver.find_elements(By.XPATH, "//table//tr")
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                for cell in cells:
                    if cell.text.strip().replace(" ", "") == self.order_number.replace(" ", ""):
                        print("\n✅ Заказ найден!\n" + "-" * 40)
                        print(row.text)
                        print("-" * 40)

                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
                        time.sleep(0.5)

                        self.safe_click(row.find_element(By.XPATH, ".//td"), "строка заказа")
                        return True

            print(f"🔄 Прокрутка вниз, попытка {scroll_attempts + 1}")
            self.driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(1)
            scroll_attempts += 1

        print("❌ Заказ не найден после прокрутки.")
        return False

    def get_overlapping_element(self, element):
        """Проверяем, не перекрыт ли элемент другим."""
        return self.driver.execute_script("""
            var elem = arguments[0];
            var rect = elem.getBoundingClientRect();
            var x = rect.left + rect.width / 2;
            var y = rect.top + rect.height / 2;
            return document.elementFromPoint(x, y);
        """, element)

    def safe_click(self, element, name="элемент"):
        """Кликаем с защитой от ошибок и перекрытий."""
        try:
            element.click()
            print(f"🖱️ Клик по '{name}' — обычным способом.")
        except ElementClickInterceptedException:
            print(f"⚠️ '{name}' перекрыт. Пробуем JS-клик.")
            try:
                self.driver.execute_script("arguments[0].click();", element)
                print(f"✅ JS-клик по '{name}' прошёл.")
            except Exception as e:
                print(f"❌ Не удалось кликнуть по '{name}': {e}")
        except StaleElementReferenceException:
            print(f"⚠️ Элемент '{name}' устарел (stale).")

    def click_schedule_button(self):
        """Нажимаем кнопку 'Запланировать поставку', если доступна."""
        if not self.driver:
            print("🚫 Драйвер не инициализирован, пропускаем клик по кнопке.")
            return

        print("⏳ Ожидание загрузки кнопки 'Запланировать поставку'...")
        try:
            button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Запланировать поставку']]"))
            )
        except TimeoutException:
            print("❌ Кнопка не найдена.")
            input("🟡 Нажмите Enter для выхода...")
            return

        # Проверка перекрытия кнопки
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        time.sleep(0.5)

        overlapping_elem = self.get_overlapping_element(button)
        if overlapping_elem and overlapping_elem != button:
            print(f"⚠️ Кнопка перекрыта элементом: <{overlapping_elem.tag_name}> с классами '{overlapping_elem.get_attribute('class')}'")
            try:
                self.driver.execute_script("arguments[0].style.display='none';", overlapping_elem)
                print("🧹 Перекрывающий элемент скрыт.")
            except Exception as e:
                print("❌ Ошибка при скрытии элемента:", e)
        else:
            print("✅ Кнопка доступна.")

        self.safe_click(button, "кнопка 'Запланировать поставку'")

    def schedule_first_available_date(self, dates_list, timeout=15):
        wait = WebDriverWait(self.driver, timeout)
        actions = ActionChains(self.driver)

        for date_str in dates_list:
            try:
                wait.until(EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, 'td[class*="Calendar-cell"]')
                ))
                cells = self.driver.find_elements(By.CSS_SELECTOR, 'td[class*="Calendar-cell"]')
                print(f"Найдено ячеек с датами: {len(cells)} для даты {date_str}")

                found_cell = None
                for cell in cells:
                    try:
                        date_span = cell.find_element(By.CSS_SELECTOR, 'span[class*="Text--body-m-bold"]')
                        if date_span.text.strip() == date_str:
                            try:
                                cell.find_element(By.XPATH, './/span[contains(text(), "Пока недоступно")]')
                                print(f"❌ Дата '{date_str}' найдена, но недоступна.")
                                continue
                            except NoSuchElementException:
                                found_cell = cell
                                break
                    except NoSuchElementException:
                        continue

                if found_cell is None:
                    print(f"⛔ Дата {date_str} не доступна или не найдена.")
                    continue

                actions.move_to_element(found_cell).perform()
                print(f"🖱️ Наведён курсор на ячейку с датой '{date_str}'")
                time.sleep(0.3)  # Дать popup'у проявиться

                # Ждём кнопку внутри ячейки — это важно
                choose_button = WebDriverWait(found_cell, timeout).until(
                    lambda el: el.find_element(By.XPATH, './/button[.//span[text()="Выбрать"]]')
                )
                print("✅ Кнопка 'Выбрать' появилась")

                # Скролл + попытка обычного клика
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", choose_button)
                time.sleep(0.2)

                try:
                    choose_button.click()
                    print("✅ Кнопка 'Выбрать' нажата (обычный клик)")
                except Exception as e:
                    print(f"⚠️ Обычный клик не удался: {e}, пробуем JS")
                    self.driver.execute_script("arguments[0].click();", choose_button)
                    print("✅ Кнопка 'Выбрать' нажата через JS")

                # Кнопка 'Запланировать'
                schedule_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="Запланировать"]]'))
                )
                schedule_button.click()
                print(f"📅 Дата '{date_str}' успешно запланирована.")
                return True

            except (NoSuchElementException, TimeoutException) as e:
                print(f"⚠️ Ошибка при обработке даты '{date_str}': {e}")
                continue
            except Exception as e:
                print(f"🔥 Непредвиденная ошибка при дате '{date_str}': {e}")
                continue

        print("🚫 Не удалось запланировать ни одну из дат.")
        return False
    
    def reload_page(self):
        print("🔄 Перезагружаем страницу...")
        self.driver.refresh()
        print("✅ Страница перезагружена")

    def cleanup(self):
        """Закрываем браузер."""
        if self.driver:
            try:
                self.driver.quit()
                print("🚪 Браузер закрыт.")
            except Exception:
                print("🔒 Браузер уже был закрыт или не запускался.")

    def run(self):
        """Основной запуск с повтором при неудаче."""
        if not self.driver:
            print("🚫 WebDriver не был инициализирован. Завершаем.")
            return

        try:
            if not self.open_page("https://seller.wildberries.ru/supplies-management/all-supplies"):
                return

            found = self.find_order_row()
            if not found:
                print("❌ Заказ не найден.")
                return

            attempt = 1
            while True:
                print(f"\n🔁 Попытка #{attempt}")
                self.click_schedule_button()

                try:
                    success = self.schedule_first_available_date(self.dates_list)
                    if success:
                        print("🎉 Успешно запланировано. Завершаем.")
                        break
                    else:
                        print("⚠️ Не удалось запланировать. Перезагружаем страницу...")
                except Exception as e:
                    print(f"🔥 Ошибка при планировании: {e}. Перезагружаем страницу...")

                self.reload_page()
                time.sleep(1)
                attempt += 1

        except TimeoutException:
            print("⏳ Время ожидания элемента истекло.")
        except WebDriverException as e:
            print(f"❌ Ошибка WebDriver: {e}")
        except Exception as e:
            print(f"⚠️ Непредвиденная ошибка: {e}")
        finally:
            self.cleanup()



if __name__ == "__main__":
    try:
        order_number = input("Введите номер заказа, который нужно найти: ").strip()
        weekdays_input = input("Введите дни недели (например: пн, ср, пт): ").strip()

        matched_dates = get_dates_by_weekdays(weekdays_input)
        if matched_dates:
            print("\n📅 Ближайшие даты:")
            for date in matched_dates:
                print("—", date)
        else:
            print("⚠️ Не удалось определить даты.")

        user_data_path = get_local_user_data_path()
        profile = "Default"
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        chromedriver_path = os.path.join(script_dir, "chromedriver-win64", "chromedriver.exe")
        
        dates_list = get_dates_by_weekdays(weekdays_input)

        bot = WBOrderFinder(order_number, user_data_path, profile, chromedriver_path, dates_list)
        bot.run()
    except Exception as e:
        print(f"❌ Ошибка в основном блоке: {e}")


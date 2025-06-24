from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import time
import os


class ChatGPTAutomation:
    def __init__(self, headless = False):
        self.driver = None
        self.wait = None
        self.setup_driver(headless)

    def setup_driver(self, headless = False):
        """Set up Chrome WebDriver with options."""
        chrome_options = webdriver.ChromeOptions()

        if headless:
            chrome_options.add_argument("--headless")

        # Additional options for stability
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--enable-unsafe-swiftshader")


        # Use webdriver-manage for automatic ChromeDriver management
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)


        print("Chrome WebDriver initialized successfully")

    
    def navigate_to_chatgpt(self):
        """Navigate to ChatGPT website"""
        try:
            self.driver.get("https://chatgpt.com")
            print("Navigated to ChatGPT website")
            return True
        except Exception as e:
            print(f"Error navigating to ChatGPT: {e}")
            return False
        
    def wait_for_login(self):
        """Wait for login to complete"""
        print("Please log in to ChatGPT mannually")
        input("Press Enter after you have successfully logged in and can see the chat interface...")

        # Wiat for chat interface to be ready
        try:
            self.wait.until(EC.presence_of_element_located(By.TAG_NAME, "textarea"))
            print("Chat interface detected")
            return True
        except Exception as e:
            print(f"Could not detect chat interface: {e}")
            return False
    
    def send_message(self, message):
        """Send a message to ChatGPT"""
        try:
            # Find the textarea input field
            message_input = self.wait.until(EC.element_to_be_clickable(By.XPATH, "//textarea[@id='root']"))

            # Clear any existing text and send new message
            message_input.clear()
            message_input.send_keys(message)

            # Send the message(enter)
            message_input.send_keys(Keys.ENTER)

            print(f"Message sent: {message}")
            return True
        
        except Exception as e:
            print(f"Error sending message: {e}")
            # Try alternative selector
            try:
                message_input = self.driver.find_element(By.TAG_NAME, "textarea")
                message_input.clear()
                message_input.send_keys(message)
                message_input.send_keys(Keys.RETURN)
                print(f"Message sent using alternative method: {message}")
                return True
            except Exception as e2:
                print(f"Failed with alternative method too: {e2}")
                return False
            
    def wait_for_response_completion(self, timeout = 60):
        """Wait until ChatGPT finishes generating response"""
        print("Waiting for response completion...")

        previous_text = ""
        stable_count = 0
        required_stable_count = 3

        for i in range(timeout):
            try:
                # Get all assistant messages:
                assistant_messages = self.driver.find_elements(
                    By.XPATH, "//div[@data-message-author-role='assistant']"
                )

                if assistant_messages:
                    current_text = assistant_messages[-1].text

                    # Check if text has stablized
                    if current_text == previous_text and len(current_text) > 0:
                        stable_count += 1
                        if stable_count >= required_stable_count:
                            print("Response completed")
                            return True
                        
                    else:
                        stable_count = 0
                        previous_text = current_text

                time.sleep(1)
            
            except Exception as e:
                print(f"Error waiting for response completion: {e}")
                time.sleep(1)

        print("Timeout waiting for response completion")
        return False
    
    def get_last_response(self):
        """Get the most recent ChatGPT response"""
        try:
            # Wait a bit to ensure response is fully loaded
            time.sleep(2)

            # Find all assistant messages
            assistant_messages = self.driver.find_elements(
                By.XPATH, "//div[@data-message-author-role='assistant']"
            )
            
            if assistant_messages:
                last_response = assistant_messages[-1].text
                print(f"Retrieved response: {last_response[:100]}...")
                return last_response
            else:
                print("No assistant messages found")
                return None
                
        except Exception as e:
            print(f"Error getting last response: {e}")
            return None
        
    def start_chat(self):
        """Start a new chat session"""
        try:
            # Navigate to ChatGPT
            if not self.navigate_to_chatgpt():
                return False
            
            # Wait for login
            if not self.wait_for_login():
                return False
            
            print("Chat session started")
            self.send_message("Hello, how are you?")
        
        except Exception as e:
            print(f"Error starting chat: {e}")
            return False
        
if __name__ == "__main__":
    chatbot = ChatGPTAutomation(headless = False)
    chatbot.start_chat()
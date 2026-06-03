# WE Quota Widget

A lightweight, background-running Windows widget to monitor your WE internet quota, built with Python and CustomTkinter. 
<img width="411" height="179" alt="Screenshot 2026-06-03 081407" src="https://github.com/user-attachments/assets/b07ea520-a01b-4dda-98e3-a2a4832b270b" />

**Feel free to fork this project, modify the widget, or add new features! The source code is open for anyone to use, edit, and improve.**

---

## 🛠️ Build Instructions for Developers

Follow these steps to compile the Python script into a standalone Windows executable (`.exe`) and create a setup installer.

### Prerequisites
1. **Install Python:** Download and install [Python](https://www.python.org/downloads/). 
   *⚠️ Important: During installation, make sure to check the box that says **"Add Python to PATH"**.*
2. **Install Inno Setup:** Download and install [Inno Setup](https://jrsoftware.org/isdl.php) (used for creating the final Windows installer).

### Step 1: Install Required Libraries
Open your Command Prompt (CMD) or Terminal as Administrator and run the following command to install all necessary Python dependencies:

```bash
pip install customtkinter pillow selenium webdriver-manager pystray pywin32 winotify pyinstaller
```
### Step 2: Compile to .EXE
Ensure that we_widget.py, app_icon.ico, and tray_icon.ico are all in the same folder. Run this PyInstaller command to compile the script into a single executable file:

```bash
pyinstaller --noconsole --onefile --icon=app_icon.ico --add-data "app_icon.ico;." --add-data "tray_icon.ico;." --hidden-import="selenium.webdriver.chrome.webdriver" --hidden-import="selenium.webdriver.chrome.options" --hidden-import="selenium.webdriver.chrome.service" we_widget.py
```
Once finished, you will find your standalone we_widget.exe inside the newly created dist folder.

### Step 3: Create the Windows Installer
1. Move the generated we_widget.exe from the dist folder back to the main project folder.

2. Open the we_widget_installer.iss file using Inno Setup.

3. Click the Compile button (or press Ctrl+F9) at the top of the window.

4. Done! You will find your final installer file ready to be shared with users.

# GestureFlow — Hand Gesture Controller

GestureFlow uses a webcam and hand tracking to control desktop audio and interact with presentations. The Flask app provides a local browser interface; `Rgesture.py` is a standalone gesture-control script.

## Requirements

The Python dependencies are listed in [`requirements.txt`](requirements.txt):

| Package | Purpose |
| --- | --- |
| Flask | Local web interface and application routes |
| opencv-python | Webcam capture and image processing |
| mediapipe 0.10.21 | Hand landmark detection |
| pyautogui | Desktop keyboard actions |
| numpy 1.26.4 | Numeric operations used by gesture controls |
| pycaw | Windows audio volume control |
| comtypes | Windows COM support for audio control |
| pywin32 | Windows APIs and PowerPoint automation |

The audio controls and desktop actions are designed for Windows. A webcam is required. To load and present PowerPoint files, install Microsoft PowerPoint. Alternatively, slide conversion can use LibreOffice and Poppler (`pdftoppm`) if PowerPoint automation is unavailable.

## Setup

Use Python on Windows, then install the project dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

Start the browser-based app:

```powershell
python app.py
```

The app opens at [http://127.0.0.1:5000](http://127.0.0.1:5000). Allow webcam access and keep the app running while using gesture controls.

To run the standalone controller instead:

```powershell
python Rgesture.py
```

Run only one controller at a time so that the processes do not compete for the webcam.

import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import math
import time
import threading
import webbrowser
import os
import uuid
import subprocess
import shutil

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from pycaw.pycaw import AudioUtilities

try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
SLIDE_DIR = os.path.join(BASE_DIR, "slides")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SLIDE_DIR, exist_ok=True)


webcam = cv2.VideoCapture(0)

hands = mp.solutions.hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

draw = mp.solutions.drawing_utils


devices = AudioUtilities.GetSpeakers()
volume = devices.EndpointVolume


latest_frame = None
frame_lock = threading.Lock()


last_action_time = 0

middle_start = None
ring_start = None
pinky_start = None


ppt_last_direction = None
ppt_last_action_time = 0


GESTURE_HOLD_TIME = 0.5
GESTURE_COOLDOWN = 1.5

PPT_DIRECTION_THRESHOLD = 0.16
PPT_COOLDOWN = 0.8


state = {
    "volume": 0,
    "muted": False,
    "gesture": "No hand detected",
    "action": "Waiting for gesture...",
    "camera": False,
    "presentation": False,
    "presentation_loaded": False,
    "slide": 1,
    "slide_count": 0,
    "ppt_name": "",
    "presentation_action": "No presentation loaded",
    "ppt_path": "",
    "slide_folder": ""
}


def set_action(text):
    state["action"] = text


def reset_presentation_gesture():
    global ppt_last_direction
    ppt_last_direction = None


def get_powerpoint_window():
    if win32gui is None:
        return None

    found = []

    def callback(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd)

        if not title:
            return

        title_lower = title.lower()

        if "powerpoint" in title_lower or state["ppt_name"].lower() in title_lower:
            found.append(hwnd)

    win32gui.EnumWindows(callback, None)

    return found[0] if found else None


def focus_powerpoint():
    hwnd = get_powerpoint_window()

    if hwnd is None:
        return False

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)

        time.sleep(0.08)

        return True

    except Exception:
        return False


def get_index_direction(hand):
    wrist = hand.landmark[0]
    index_tip = hand.landmark[8]

    vertical_difference = index_tip.y - wrist.y

    if vertical_difference <= -PPT_DIRECTION_THRESHOLD:
        return "up"

    if vertical_difference >= PPT_DIRECTION_THRESHOLD:
        return "down"

    return "neutral"


def presentation_key(key):
    if not state["presentation"]:
        return

    if not focus_powerpoint():
        state["presentation_action"] = "PowerPoint window not found"
        return

    pyautogui.press(key)

    if key == "right":
        state["slide"] = min(
            state["slide"] + 1,
            max(1, state["slide_count"])
        )

        state["presentation_action"] = "Next slide"

    elif key == "left":
        state["slide"] = max(
            1,
            state["slide"] - 1
        )

        state["presentation_action"] = "Previous slide"


def detect_presentation_gesture(hand):
    global ppt_last_direction
    global ppt_last_action_time

    current_time = time.time()

    direction = get_index_direction(hand)

    if direction == "neutral":
        return None

    if current_time - ppt_last_action_time < PPT_COOLDOWN:
        return None

    if direction == ppt_last_direction:
        return None

    ppt_last_direction = direction
    ppt_last_action_time = current_time

    if direction == "up":
        return "next"

    if direction == "down":
        return "previous"

    return None


def camera_loop():
    global latest_frame
    global last_action_time
    global middle_start
    global ring_start
    global pinky_start

    while True:
        success, image = webcam.read()

        if not success:
            state["camera"] = False
            time.sleep(0.05)
            continue

        state["camera"] = True

        image = cv2.flip(image, 1)

        rgb = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2RGB
        )

        result = hands.process(rgb)

        state["gesture"] = "No hand detected"

        if result.multi_hand_landmarks:
            hand = result.multi_hand_landmarks[0]

            draw.draw_landmarks(
                image,
                hand,
                mp.solutions.hands.HAND_CONNECTIONS
            )

            if state["presentation"]:

                state["gesture"] = "Point index UP / DOWN"

                presentation_gesture = detect_presentation_gesture(hand)

                if presentation_gesture == "next":
                    state["gesture"] = "Index UP → Next"

                    presentation_key("right")

                    set_action("Next slide")

                elif presentation_gesture == "previous":
                    state["gesture"] = "Index DOWN → Previous"

                    presentation_key("left")

                    set_action("Previous slide")

            else:

                reset_presentation_gesture()

                h, w, _ = image.shape

                thumb = hand.landmark[4]
                index = hand.landmark[8]
                middle = hand.landmark[12]
                ring = hand.landmark[16]
                pinky = hand.landmark[20]

                x1 = int(thumb.x * w)
                y1 = int(thumb.y * h)

                x2 = int(index.x * w)
                y2 = int(index.y * h)

                x3 = int(middle.x * w)
                y3 = int(middle.y * h)

                x4 = int(ring.x * w)
                y4 = int(ring.y * h)

                x5 = int(pinky.x * w)
                y5 = int(pinky.y * h)

                index_distance = math.hypot(
                    x2 - x1,
                    y2 - y1
                )

                middle_distance = math.hypot(
                    x3 - x1,
                    y3 - y1
                )

                ring_distance = math.hypot(
                    x4 - x1,
                    y4 - y1
                )

                pinky_distance = math.hypot(
                    x5 - x1,
                    y5 - y1
                )

                volume_percent = int(
                    np.interp(
                        index_distance,
                        [20, 120],
                        [0, 100]
                    )
                )

                volume_percent = max(
                    0,
                    min(
                        100,
                        volume_percent
                    )
                )

                volume.SetMasterVolumeLevelScalar(
                    volume_percent / 100,
                    None
                )

                state["volume"] = volume_percent

                current_time = time.time()

                if middle_distance < 30:

                    state["gesture"] = "Minimize"

                    if middle_start is None:
                        middle_start = current_time

                    elif (
                        current_time - middle_start >= GESTURE_HOLD_TIME
                        and current_time - last_action_time > GESTURE_COOLDOWN
                    ):

                        pyautogui.hotkey(
                            "alt",
                            "space"
                        )

                        pyautogui.press("n")

                        last_action_time = current_time
                        middle_start = None

                        set_action(
                            "Minimize command triggered"
                        )

                else:
                    middle_start = None

                if ring_distance < 30:

                    state["gesture"] = "Maximize"

                    if ring_start is None:
                        ring_start = current_time

                    elif (
                        current_time - ring_start >= GESTURE_HOLD_TIME
                        and current_time - last_action_time > GESTURE_COOLDOWN
                    ):

                        pyautogui.hotkey(
                            "win",
                            "up"
                        )

                        last_action_time = current_time
                        ring_start = None

                        set_action(
                            "Maximize command triggered"
                        )

                else:
                    ring_start = None

                if pinky_distance < 30:

                    state["gesture"] = "Mute"

                    if pinky_start is None:
                        pinky_start = current_time

                    elif (
                        current_time - pinky_start >= GESTURE_HOLD_TIME
                        and current_time - last_action_time > GESTURE_COOLDOWN
                    ):

                        current_mute = volume.GetMute()

                        volume.SetMute(
                            not current_mute,
                            None
                        )

                        state["muted"] = not current_mute

                        last_action_time = current_time
                        pinky_start = None

                        if current_mute:
                            set_action("Unmuted")
                        else:
                            set_action("Muted")

                else:
                    pinky_start = None

                cv2.putText(
                    image,
                    f"Volume: {volume_percent}%",
                    (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2
                )

        else:
            reset_presentation_gesture()

        if state["presentation"]:

            cv2.putText(
                image,
                "PRESENTATION MODE",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 220, 255),
                2
            )

            cv2.putText(
                image,
                "INDEX UP = NEXT  |  INDEX DOWN = PREVIOUS",
                (20, 85),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2
            )

        cv2.putText(
            image,
            state["gesture"],
            (20, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2
        )

        success, encoded = cv2.imencode(
            ".jpg",
            image
        )

        if success:
            with frame_lock:
                latest_frame = encoded.tobytes()

        time.sleep(0.01)


def generate_frames():
    while True:

        with frame_lock:
            frame = latest_frame

        if frame is not None:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame
                + b"\r\n"
            )

        time.sleep(0.03)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video")
def video():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/state")
def get_state():
    return jsonify(state)


def open_browser():
    time.sleep(1.5)

    webbrowser.open(
        "http://127.0.0.1:5000"
    )


def clear_folder(folder):
    if not os.path.exists(folder):
        return

    for name in os.listdir(folder):

        path = os.path.join(
            folder,
            name
        )

        try:

            if os.path.isdir(path):
                shutil.rmtree(path)

            else:
                os.remove(path)

        except OSError:
            pass


def convert_with_powerpoint(
    ppt_path,
    output_dir
):
    try:
        import win32com.client
    except ImportError:
        return (
            False,
            "pywin32 is not installed"
        )

    powerpoint = None
    presentation = None

    try:

        powerpoint = win32com.client.DispatchEx(
            "PowerPoint.Application"
        )

        powerpoint.Visible = True

        presentation = powerpoint.Presentations.Open(
            os.path.abspath(ppt_path),
            ReadOnly=True,
            WithWindow=False
        )

        slide_count = presentation.Slides.Count

        if slide_count == 0:
            return (
                False,
                "PowerPoint contains no slides"
            )

        for index in range(
            1,
            slide_count + 1
        ):

            slide = presentation.Slides(index)

            output_file = os.path.join(
                output_dir,
                f"slide-{index:04d}.jpg"
            )

            slide.Export(
                output_file,
                "JPG",
                1600,
                900
            )

        return (
            True,
            f"Exported {slide_count} slides"
        )

    except Exception as e:

        return (
            False,
            f"PowerPoint error: {e}"
        )

    finally:

        try:
            if presentation is not None:
                presentation.Close()
        except Exception:
            pass

        try:
            if powerpoint is not None:
                powerpoint.Quit()
        except Exception:
            pass


def convert_with_libreoffice(
    ppt_path,
    output_dir
):

    soffice = (
        shutil.which("soffice")
        or shutil.which("libreoffice")
    )

    pdftoppm = shutil.which("pdftoppm")

    if not soffice:
        return (
            False,
            "LibreOffice (soffice) was not found"
        )

    if not pdftoppm:
        return (
            False,
            "Poppler (pdftoppm) was not found"
        )

    filename = os.path.basename(
        ppt_path
    )

    try:

        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                output_dir,
                ppt_path
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        pdf_name = (
            os.path.splitext(filename)[0]
            + ".pdf"
        )

        pdf_path = os.path.join(
            output_dir,
            pdf_name
        )

        if not os.path.exists(pdf_path):
            return (
                False,
                "LibreOffice did not create the PDF"
            )

        subprocess.run(
            [
                pdftoppm,
                "-jpeg",
                "-r",
                "110",
                pdf_path,
                os.path.join(
                    output_dir,
                    "slide"
                )
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        generated = sorted(
            name
            for name in os.listdir(output_dir)
            if name.startswith("slide-")
            and name.endswith(".jpg")
        )

        for index, name in enumerate(
            generated,
            start=1
        ):

            source = os.path.join(
                output_dir,
                name
            )

            target = os.path.join(
                output_dir,
                f"slide-{index:04d}.jpg"
            )

            if os.path.abspath(source) != os.path.abspath(target):
                os.replace(
                    source,
                    target
                )

        return (
            len(generated) > 0,
            f"Exported {len(generated)} slides"
        )

    except Exception as e:

        return (
            False,
            f"LibreOffice error: {e}"
        )


@app.route(
    "/upload-ppt",
    methods=["POST"]
)
def upload_ppt():

    file = request.files.get("ppt")

    if not file or not file.filename:
        return jsonify({
            "error": "No PowerPoint file selected"
        }), 400

    if not file.filename.lower().endswith(
        (".pptx", ".ppt")
    ):
        return jsonify({
            "error": "Please upload a .ppt or .pptx file"
        }), 400

    clear_folder(UPLOAD_DIR)
    clear_folder(SLIDE_DIR)

    filename = os.path.basename(
        file.filename
    )

    ppt_path = os.path.join(
        UPLOAD_DIR,
        filename
    )

    file.save(ppt_path)

    output_dir = os.path.join(
        SLIDE_DIR,
        uuid.uuid4().hex
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    converted, message = convert_with_powerpoint(
        ppt_path,
        output_dir
    )

    if not converted:

        fallback_converted, fallback_message = convert_with_libreoffice(
            ppt_path,
            output_dir
        )

        if not fallback_converted:

            shutil.rmtree(
                output_dir,
                ignore_errors=True
            )

            return jsonify({
                "error":
                f"{message}\n\nFallback: {fallback_message}"
            }), 500

        message = fallback_message

    slides = sorted(
        name
        for name in os.listdir(output_dir)
        if name.startswith("slide-")
        and name.endswith(".jpg")
    )

    if not slides:

        shutil.rmtree(
            output_dir,
            ignore_errors=True
        )

        return jsonify({
            "error": "No slide images were created"
        }), 500

    state["presentation"] = False
    state["presentation_loaded"] = True
    state["slide"] = 1
    state["slide_count"] = len(slides)
    state["ppt_name"] = filename
    state["ppt_path"] = ppt_path
    state["slide_folder"] = os.path.basename(output_dir)
    state["presentation_action"] = "Presentation loaded"

    reset_presentation_gesture()

    return jsonify({
        "success": True,
        "name": filename,
        "slides": len(slides),
        "folder": os.path.basename(output_dir),
        "message": message
    })


@app.route(
    "/slides/<folder>/<filename>"
)
def slide_file(
    folder,
    filename
):

    return send_from_directory(
        os.path.join(
            SLIDE_DIR,
            folder
        ),
        filename
    )


@app.route(
    "/presentation-action/<action>",
    methods=["POST"]
)
def presentation_action(action):

    if action not in (
        "start",
        "exit"
    ):
        return jsonify({
            "error": "Only start and exit are available"
        }), 400

    if action == "start":

        if not state["ppt_path"]:
            return jsonify({
                "error": "No PowerPoint loaded"
            }), 400

        if not os.path.exists(
            state["ppt_path"]
        ):
            return jsonify({
                "error": "PowerPoint file not found"
            }), 400

        try:

            os.startfile(
                state["ppt_path"]
            )

            time.sleep(2)

            focus_powerpoint()

            pyautogui.press("f5")

            time.sleep(1)

            focus_powerpoint()

            state["presentation"] = True
            state["presentation_action"] = "Presentation started"

            reset_presentation_gesture()

        except Exception as e:

            return jsonify({
                "error": f"Could not start PowerPoint: {e}"
            }), 500

    elif action == "exit":

        try:

            focus_powerpoint()

            pyautogui.press("esc")

        except Exception:
            pass

        state["presentation"] = False
        state["presentation_action"] = "Presentation exited"

        reset_presentation_gesture()

    return jsonify({
        "success": True,
        "presentation": state["presentation"],
        "slide": state["slide"],
        "action": state["presentation_action"]
    })


if __name__ == "__main__":

    camera_thread = threading.Thread(
        target=camera_loop,
        daemon=True
    )

    camera_thread.start()

    browser_thread = threading.Thread(
        target=open_browser,
        daemon=True
    )

    browser_thread.start()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
    )
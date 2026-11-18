import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import math
import time
from pycaw.pycaw import AudioUtilities

webcam = cv2.VideoCapture(0)

hands = mp.solutions.hands.Hands(
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

draw = mp.solutions.drawing_utils

devices = AudioUtilities.GetSpeakers()
volume = devices.EndpointVolume

last_action_time = 0
cooldown = 1.5
muted = False
last_action_time = 0
cooldown = 1.5

middle_start = None
ring_start = None
pinky_start = None

muted = False

HOLD_TIME = 0.5

while True:
    success, image = webcam.read()

    if not success:
        break

    image = cv2.flip(image, 1)

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)

    if result.multi_hand_landmarks:

        for hand in result.multi_hand_landmarks:

            draw.draw_landmarks(
                image,
                hand,
                mp.solutions.hands.HAND_CONNECTIONS
            )

            h, w, _ = image.shape

            thumb = hand.landmark[4]
            index = hand.landmark[8]
            middle = hand.landmark[12]
            ring = hand.landmark[16]
            pinky = hand.landmark[20]

            x1, y1 = int(thumb.x * w), int(thumb.y * h)
            x2, y2 = int(index.x * w), int(index.y * h)
            x3, y3 = int(middle.x * w), int(middle.y * h)
            x4, y4 = int(ring.x * w), int(ring.y * h)
            x5, y5 = int(pinky.x * w), int(pinky.y * h)

            index_distance = math.hypot(x2 - x1, y2 - y1)
            middle_distance = math.hypot(x3 - x1, y3 - y1)
            ring_distance = math.hypot(x4 - x1, y4 - y1)
            pinky_distance = math.hypot(x5 - x1, y5 - y1)

            MIN_DISTANCE = 20
            MAX_DISTANCE = 120

            volume_percent = int(
                np.interp(
                    index_distance,
                    [MIN_DISTANCE, MAX_DISTANCE],
                    [0, 100]
                )
            )

            volume_percent = max(0, min(100, volume_percent))
            volume.SetMasterVolumeLevelScalar(volume_percent / 100, None)

            cv2.putText(
                image,
                f"Volume: {volume_percent}%",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )

            current_time = time.time()

            if middle_distance < 30:
                if middle_start is None:
                    middle_start = current_time

                elif current_time - middle_start >= HOLD_TIME and current_time - last_action_time > cooldown:
                    pyautogui.hotkey('alt', 'space')
                    pyautogui.press('n')
                    last_action_time = current_time
                    middle_start = None
            else:
                middle_start = None

            if ring_distance < 30:
                if ring_start is None:
                    ring_start = current_time

                elif current_time - ring_start >= HOLD_TIME and current_time - last_action_time > cooldown:
                    pyautogui.hotkey('win', 'up')
                    last_action_time = current_time
                    ring_start = None
            else:
                ring_start = None

            if pinky_distance < 30:
                if pinky_start is None:
                    pinky_start = current_time

                elif current_time - pinky_start >= HOLD_TIME and current_time - last_action_time > cooldown:
                    muted = not muted
                    volume.SetMute(muted, None)
                    last_action_time = current_time
                    pinky_start = None
            else:
                pinky_start = None

    cv2.imshow("Gesture Desktop Controller", image)

    if cv2.waitKey(1) & 0xFF == 27:
        break

webcam.release()
cv2.destroyAllWindows()

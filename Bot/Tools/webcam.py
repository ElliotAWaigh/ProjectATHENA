import cv2
import mediapipe as mp

# Initialize Mediapipe Hand model
mp_hands = mp.solutions.hands
hands = mp_hands.Hands()
mp_draw = mp.solutions.drawing_utils

def detect_gesture(hand_landmarks):
    # Get the coordinates of relevant landmarks
    thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
    index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
    middle_tip = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
    ring_tip = hand_landmarks.landmark[mp_hands.HandLandmark.RING_FINGER_TIP]
    pinky_tip = hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_TIP]
    wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]

    # Example gesture detection: Thumbs Up
    if thumb_tip.y < wrist.y and all([index_tip.y > wrist.y, middle_tip.y > wrist.y, ring_tip.y > wrist.y, pinky_tip.y > wrist.y]):
        return "Thumbs Up"
    # Example gesture detection: Open Palm
    elif all([thumb_tip.y < wrist.y, index_tip.y < wrist.y, middle_tip.y < wrist.y, ring_tip.y < wrist.y, pinky_tip.y < wrist.y]):
        return "Open Palm"
    else:
        return "Unknown Gesture"

# Open the webcam
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Convert the image from BGR to RGB
    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Process the RGB image to detect hands
    results = hands.process(img_rgb)

    # If hands are detected, draw the landmarks and detect gestures
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            gesture = detect_gesture(hand_landmarks)
            cv2.putText(frame, gesture, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

    # Display the resulting frame
    cv2.imshow('Webcam Feed', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the webcam and close windows
cap.release()
cv2.destroyAllWindows()

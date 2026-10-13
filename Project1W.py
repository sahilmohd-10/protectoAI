from ultralytics import YOLO
import cv2
import cvzone
import math

cap = cv2.VideoCapture(0)

# Set the desired resolution for the webcam. This can help with performance.
cap.set(3, 1280)  # Width
cap.set(4, 720)  # Height

# Load the YOLO model.
model = YOLO("best.pt")

# List of class names and a color for drawing.
classNames = ['Excavator', 'Gloves', 'Hardhat', 'Ladder', 'Mask', 'NO-Hardhat', 'NO-Mask', 'NO-Safety Vest', 'Person',
              'SUV', 'Safety Cone', 'Safety Vest', 'bus', 'dump truck', 'fire hydrant', 'machinery', 'mini-van',
              'sedan', 'semi', 'trailer', 'truck and trailer', 'truck', 'van', 'vehicle', 'wheel loader']
myColor = (0, 0, 255)

# Check if the webcam is opened successfully.
if not cap.isOpened():
    print("Error: Could not open webcam. Please check your camera index or if another program is using it.")
    exit()

while True:
    # Read a frame from the webcam.
    success, img = cap.read()
    if not success:
        print("Error: Failed to read frame from webcam.")
        break

    # Perform object detection on the current frame.
    results = model(img, stream=True)

    # Loop through the detection results.
    for r in results:
        boxes = r.boxes
        for box in boxes:
            # Extract bounding box coordinates.
            x1, y1, x2, y2 = box.xyxy[0]
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            w, h = x2 - x1, y2 - y1
            cvzone.cornerRect(img, (x1, y1, w, h))

            # Extract confidence score and class name.
            conf = math.ceil((box.conf[0] * 100)) / 100
            cls = int(box.cls[0])

            # Draw the class name and confidence on the image.
            cvzone.putTextRect(img, f'{classNames[cls]} {conf}', (max(0, x1), max(35, y1)), scale=1, thickness=1,
                               colorR=myColor)

    # Display the processed image.
    cv2.imshow("Image", img)

    # Wait for a key press and exit if 'q' is pressed.
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the webcam and destroy all windows.
cap.release()
cv2.destroyAllWindows()
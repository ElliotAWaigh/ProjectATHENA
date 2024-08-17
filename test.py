from object_detector import *
# Load Object Detector
detector = HomogeneousBgDetector()
...
contours = detector.detect_objects(img)

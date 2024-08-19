import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from sklearn.model_selection import train_test_split
import numpy as np
import os
from glob import glob
import cv2

# Path to the dataset
dataset_path = 'path/to/your/dataset'

# Image dimensions
IMG_HEIGHT, IMG_WIDTH = 128, 128

# Load and preprocess the data
images = []
labels = []

for label_dir in os.listdir(dataset_path):
    label_path = os.path.join(dataset_path, label_dir)
    for img_path in glob(os.path.join(label_path, '*.jpg')):
        img = cv2.imread(img_path)
        img = cv2.resize(img, (IMG_WIDTH, IMG_HEIGHT))
        img = img / 255.0  # Normalize to [0, 1]
        images.append(img)
        labels.append(label_dir)

images = np.array(images)
labels = np.array(labels)

# Encode labels as integers
label_names = sorted(set(labels))
label_map = {name: i for i, name in enumerate(label_names)}
labels = np.array([label_map[label] for label in labels])

# Split the data into training, validation, and test sets
X_train, X_test, y_train, y_test = train_test_split(images, labels, test_size=0.2, random_state=42)
X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, test_size=0.2, random_state=42)

# Convert labels to categorical
y_train = tf.keras.utils.to_categorical(y_train, num_classes=len(label_names))
y_val = tf.keras.utils.to_categorical(y_val, num_classes=len(label_names))
y_test = tf.keras.utils.to_categorical(y_test, num_classes=len(label_names))

model = models.Sequential([
    layers.Conv2D(32, (3, 3), activation='relu', input_shape=(IMG_HEIGHT, IMG_WIDTH, 3)),
    layers.MaxPooling2D((2, 2)),
    layers.Conv2D(64, (3, 3), activation='relu'),
    layers.MaxPooling2D((2, 2)),
    layers.Conv2D(128, (3, 3), activation='relu'),
    layers.MaxPooling2D((2, 2)),
    layers.Flatten(),
    layers.Dense(128, activation='relu'),
    layers.Dropout(0.5),
    layers.Dense(len(label_names), activation='softmax')
])

model.compile(optimizer='adam',
              loss='categorical_crossentropy',
              metrics=['accuracy'])

datagen = ImageDataGenerator(
    rotation_range=20,
    width_shift_range=0.2,
    height_shift_range=0.2,
    horizontal_flip=True
)

datagen.fit(X_train)

history = model.fit(
    datagen.flow(X_train, y_train, batch_size=32),
    validation_data=(X_val, y_val),
    epochs=10
)

test_loss, test_acc = model.evaluate(X_test, y_test)
print(f'Test accuracy: {test_acc:.4f}')

model.save('hand_gesture_model.h5')
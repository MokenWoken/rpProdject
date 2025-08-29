import pygame
import keyboard  # requires: pip install keyboard

# init audio
pygame.mixer.init()

# load sounds
sound_a = pygame.mixer.Sound("beep.wav")
sound_b = pygame.mixer.Sound("sheepbleat.wav")

print("Press A or B to play sounds. Press ESC to quit.")

while True:
    if keyboard.is_pressed("a"):
        sound_a.play()
    elif keyboard.is_pressed("b"):
        sound_b.play()
    elif keyboard.is_pressed("esc"):
        break

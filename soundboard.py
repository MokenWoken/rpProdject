import pygame
import sys
import termios
import tty

# Init pygame mixer
pygame.mixer.init()

# Load sounds
sound_a = pygame.mixer.Sound("beep.wav")
sound_b = pygame.mixer.Sound("sheepbleat.wav")

# Function to capture single key presses
def getch():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

print("Press A or B to play sounds. Press ESC to quit.")

while True:
    key = getch()
    if key.lower() == 'a':
        sound_a.play()
    elif key.lower() == 'b':
        sound_b.play()
    elif ord(key) == 27:  # ESC
        break

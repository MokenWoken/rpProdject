import pygame, sys, termios, tty, random, json

# Init mixer (tuned for Pi 1)
pygame.mixer.pre_init(22050, -16, 1, 1024)
pygame.init()
pygame.mixer.init()

# --- Utility functions ---

def play(sound_or_list):
    """Play one sound (or random from a list) and block until finished."""
    sound = random.choice(sound_or_list) if isinstance(sound_or_list, list) else sound_or_list
    sound.play()
    while pygame.mixer.get_busy():
        pygame.time.delay(50)

def getch():
    """Capture one raw key press."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def load_sound_list(filenames):
    """Load .wav files into pygame Sound objects."""
    return [pygame.mixer.Sound(f) for f in filenames]

# --- Load stage data ---

with open("stages.json", "r") as f:
    stages_data = json.load(f)

stages = []
for s in stages_data:
    stages.append({
        "prompt": load_sound_list(s["prompt"]),
        "correct": s["correct"].lower(),
        "success": load_sound_list(s["success"]),
        "fail": load_sound_list(s["fail"])
    })

# Load global feedback sounds
beep = pygame.mixer.Sound("beep.wav")
buzzer = pygame.mixer.Sound("buzzer.wav")

print("Game starting...")

# --- Stage loop ---
for stage in stages:
    # Play the prompt ONCE at the start of the stage
    play(stage["prompt"])

    while True:
        key = getch().lower()

        if key == stage["correct"]:
            play(beep)                  # universal feedback
            play(stage["success"])      # JSON success sound(s)
            print("Correct!")
            break  # advance to next stage

        else:
            play(buzzer)                # always play buzzer first
            play(stage["fail"])         # then JSON fail sound(s)
            print("Wrong, try again...")  # then immediately wait for next input

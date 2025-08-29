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
    stage = {
        "prompt": load_sound_list(s["prompt"]),
        "correct": s["correct"],  # may be string or list
        "success": load_sound_list(s["success"]),
        "fail": {k.lower(): load_sound_list(v) for k, v in s.get("fail", {}).items()},
        "fail_default": load_sound_list(s.get("fail_default", []))
    }
    stages.append(stage)

# Load global feedback sounds
beep = pygame.mixer.Sound("beep.wav")
buzzer = pygame.mixer.Sound("beep.wav")
# Background music
#bg_music = pygame.mixer.Sound("background.wav")
music_channel = pygame.mixer.Channel(0)
music_channel.play(bg_music, loops=-1)  # play forever

print("Game starting...")

# --- Stage loop ---
for stage in stages:
    play(stage["prompt"])  # play prompt once

    # Keep counters for fail sequences
    fail_counters = {k: 0 for k in stage["fail"]}
    default_fail_counter = 0

    while True:
        key = getch().lower()

        # Normalize correct keys to a list
        correct_keys = stage["correct"]
        if isinstance(correct_keys, str):
            correct_keys = [correct_keys]
        correct_keys = [ck.lower() for ck in correct_keys]

        if key in correct_keys:
            play(beep)
            play(stage["success"])
            print("Correct!")
            break

        elif key in stage["fail"]:
            play(buzzer)

            sounds = stage["fail"][key]
            idx = fail_counters[key]
            play(sounds[idx])

            if idx < len(sounds) - 1:
                fail_counters[key] += 1

            print(f"Wrong key '{key}', try again...")

        elif stage["fail_default"]:
            play(buzzer)

            sounds = stage["fail_default"]
            idx = default_fail_counter
            play(sounds[idx])

            if idx < len(sounds) - 1:
                default_fail_counter += 1

            print(f"Unexpected key '{key}', fallback fail triggered.")

        else:
            # If no fallback provided, just play buzzer
            play(buzzer)
            print(f"Unexpected key '{key}', no fail sounds defined.")

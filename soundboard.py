import pygame, sys, termios, tty, random, json, time
from evdev import InputDevice, list_devices

# Init mixer (tuned for Pi 1)
pygame.mixer.pre_init(22050, -16, 1, 256)
pygame.init()
pygame.mixer.init()

# --- Utility functions ---

def play(sound_or_list):
    """Play one sound (or random from a list) and block until finished (ignores background music)."""
    sound = random.choice(sound_or_list) if isinstance(sound_or_list, list) else sound_or_list
    ch = sound.play()
    if ch is not None:
        while ch.get_busy():
            pygame.time.delay(10)

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

# --- Keyboard detection ---

from evdev import ecodes

def keyboard_connected():
    """Return True if a real USB/Bluetooth keyboard is connected."""
    devices = [InputDevice(path) for path in list_devices()]
    for dev in devices:
        try:
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                name = dev.name.lower()
                phys = (dev.phys or "").lower()

                # Filter out known false positives
                if "vc4-hdmi" in name or "gpio" in name or "virtual" in name:
                    continue

                # At this point it's likely a real keyboard
                return True
        except Exception:
            continue
    return False

def wait_for_keyboard():
    """Block until a keyboard is connected."""
    print("Waiting for keyboard...")
    while not keyboard_connected():
        time.sleep(1)
    print("Keyboard detected!")

# --- Load stage data ---

with open("stages.json", "r") as f:
    stages_data = json.load(f)

stages_by_id = {}
stage_order = []
for s in stages_data:
    stage = {
        "id": s["id"],
        "prompt": load_sound_list(s["prompt"]),
        "correct": s["correct"],
        "success": load_sound_list(s["success"]),
        "fail": {k.lower(): load_sound_list(v) for k, v in s.get("fail", {}).items()},
        "fail_default": load_sound_list(s.get("fail_default", [])),
        "next_on_success": s.get("next_on_success"),
        "next_on_fail": s.get("next_on_fail"),
        "fail_branches": s.get("fail_branches", {})
    }
    stages_by_id[stage["id"]] = stage
    stage_order.append(stage["id"])

# Load global feedback sounds
beep = pygame.mixer.Sound("beep.wav")
buzzer = pygame.mixer.Sound("buzzer.wav")

# Background music
bg_music = pygame.mixer.Sound("background.wav")
music_channel = pygame.mixer.Channel(0)
sfx_channel = pygame.mixer.Channel(1)
keypress_sounds_channel = pygame.mixer.Channel(2)
#music_channel.play(bg_music, loops=-1)
keyboard_connected_sound = pygame.mixer.Sound("keyboard_connected.wav")

# --- Load keypress sounds separately ---
with open("keypress.json", "r") as f:
    kp_data = json.load(f)

keypress_sounds = {
    k.lower(): load_sound_list(v)
    for k, v in kp_data.get("keypress_sounds", {}).items()
}
keypress_fallback = load_sound_list(kp_data.get("keypress_fallback", []))


def play_keypress_sound(key):
    """Play a random sound for this key on the keypress channel."""
    if key in keypress_sounds:
        sound = random.choice(keypress_sounds[key])
    else:
        sound = random.choice(keypress_fallback)
    keypress_sounds_channel.play(sound)

# --- Stage runner ---
def run_stages():
    current_stage_id = stage_order[0]

    while current_stage_id:
        # Check if keyboard still present
        if not keyboard_connected():
            raise RuntimeError("KeyboardDisconnected")

        stage = stages_by_id[current_stage_id]
        play(stage["prompt"])

        fail_counters = {k: 0 for k in stage["fail"]}
        default_fail_counter = 0
        fail_count = 0
        next_stage_id = None
        correct_def = stage["correct"]

        # --- Case: sequence of keys ---
        if isinstance(correct_def, list) and len(correct_def) > 0 and isinstance(correct_def[0], list):
            sequence = [k.lower() for k in correct_def[0]]
            seq_index = 0
            while seq_index < len(sequence):
                if not keyboard_connected():
                    raise RuntimeError("KeyboardDisconnected")
                key = getch().lower()
                play_keypress_sound(key)  # <-- always trigger key sound
                if key == sequence[seq_index]:
                    play(beep)
                    seq_index += 1
                else:
                    play(buzzer)
                    if stage["fail_default"]:
                        idx = default_fail_counter
                        sounds = stage["fail_default"]
                        play(sounds[idx])
                        if idx < len(sounds) - 1:
                            default_fail_counter += 1
                    print("Wrong key in sequence, restarting...")
                    seq_index = 0
            play(stage["success"])
            print("Sequence completed!")
            next_stage_id = stage.get("next_on_success")

        # --- Case: normal ---
        else:
            while True:
                if not keyboard_connected():
                    raise RuntimeError("KeyboardDisconnected")

                key = getch().lower()
                correct_keys = correct_def
                if isinstance(correct_keys, str):
                    correct_keys = [correct_keys]
                correct_keys = [ck.lower() for ck in correct_keys]

                if key in correct_keys:
                    play(beep)
                    play(stage["success"])
                    print("Correct!")
                    next_stage_id = stage.get("next_on_success")
                    break
                else:
                    fail_count += 1
                    if key in stage["fail"]:
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
                        play(buzzer)
                        print(f"Unexpected key '{key}', no fail sounds defined.")

                    # --- check fail_branches ---
                    fb = stage.get("fail_branches", {})
                    if str(fail_count) in fb:
                        branch_def = fb[str(fail_count)]
                        print("Special branch triggered. Waiting for input...")
                        branch_key = getch().lower()
                        if branch_key in branch_def["keys"]:
                            next_stage_id = branch_def["keys"][branch_key]
                            break
                        else:
                            print(f"No branch for '{branch_key}', continuing fails...")

                    # --- optional direct fail jump ---
                    if "next_on_fail" in stage and stage["next_on_fail"]:
                        next_stage_id = stage["next_on_fail"]
                        break

        # --- Move to next stage ---
        if not next_stage_id:
            current_index = stage_order.index(stage["id"])
            if current_index + 1 < len(stage_order):
                next_stage_id = stage_order[current_index + 1]
            else:
                next_stage_id = None

        current_stage_id = next_stage_id

# --- Main controller ---
while True:
    wait_for_keyboard()
    # Fade in background music when keyboard appears
    sfx_channel.play(keyboard_connected_sound)
    music_channel.play(bg_music, loops=-1, fade_ms=2000)  # 2 sec fade in
    time.sleep(1)
    try:
        run_stages()
        print("Game finished!")
        break
    except RuntimeError as e:
        if str(e) == "KeyboardDisconnected":
            print("Keyboard disconnected! Restarting from stage 1...")
            music_channel.fadeout(2000)
            continue
        else:
            raise

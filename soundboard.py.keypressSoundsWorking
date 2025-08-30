import pygame, sys, termios, tty, random, json, time, threading, queue
from evdev import InputDevice, list_devices, ecodes

# Init mixer (tuned for Pi 1)
pygame.mixer.pre_init(22050, -16, 1, 256)
pygame.init()
pygame.mixer.init()

# --- Globals ---
game_input_enabled = False
key_queue = queue.Queue()

# --- Utility functions ---
def play(sound_or_list, block=True, channel=None):
    """Play one sound (or random from list) on a given channel."""
    sound = random.choice(sound_or_list) if isinstance(sound_or_list, list) else sound_or_list
    if channel:
        channel.play(sound)
        if block:
            while channel.get_busy():
                pygame.time.delay(10)
    else:
        ch = sound.play()
        if block and ch is not None:
            while ch.get_busy():
                pygame.time.delay(10)

def play_blocking_stage_sound(sound_or_list):
    """Play a stage sound (prompt/success/fail) on the stage channel.
       During playback only keypress sounds are allowed."""
    global game_input_enabled
    game_input_enabled = False
    play(sound_or_list, block=True, channel=stage_channel)

    # flush queue of any keys pressed during playback
    while not key_queue.empty():
        try:
            key_queue.get_nowait()
        except:
            break

    game_input_enabled = True

def getch():
    """Capture one raw key press from stdin."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def key_listener():
    """Background thread to constantly read keys with getch()."""
    while True:
        key = getch().lower()
        if game_input_enabled:
            key_queue.put(key)  # feed into game logic
        else:
            play_keypress_sound(key)  # just play typing sounds

def wait_for_key():
    """Return next key that counts for game logic."""
    return key_queue.get(block=True)

def load_sound_list(filenames):
    return [pygame.mixer.Sound(f) for f in filenames]

# --- Keyboard detection ---
def keyboard_connected():
    devices = [InputDevice(path) for path in list_devices()]
    for dev in devices:
        try:
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                name = dev.name.lower()
                if "vc4-hdmi" in name or "gpio" in name or "virtual" in name:
                    continue
                return True
        except: continue
    return False

def wait_for_keyboard():
    print("Waiting for keyboard...")
    while not keyboard_connected():
        time.sleep(1)
    print("Keyboard detected!")

# --- Load stages ---
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
        "fail": {k.lower(): load_sound_list(v) for k,v in s.get("fail",{}).items()},
        "fail_default": load_sound_list(s.get("fail_default", [])),
        "next_on_success": s.get("next_on_success"),
        "next_on_fail": s.get("next_on_fail"),
        "fail_branches": s.get("fail_branches", {})
    }
    stages_by_id[stage["id"]] = stage
    stage_order.append(stage["id"])

# --- Load sounds ---
beep = pygame.mixer.Sound("beep.wav")
buzzer = pygame.mixer.Sound("buzzer.wav")
bg_music = pygame.mixer.Sound("background.wav")
keyboard_connected_sound = pygame.mixer.Sound("keyboard_connected.wav")

stage_channel = pygame.mixer.Channel(3)
music_channel = pygame.mixer.Channel(0)
sfx_channel = pygame.mixer.Channel(1)
keypress_sounds_channel = pygame.mixer.Channel(2)

# --- Keypress sounds ---
with open("keypress.json", "r") as f:
    kp_data = json.load(f)

keypress_sounds = {k.lower(): load_sound_list(v) for k,v in kp_data.get("keypress_sounds",{}).items()}
keypress_fallback = load_sound_list(kp_data.get("keypress_fallback", []))

def play_keypress_sound(key):
    if key in keypress_sounds:
        sound = random.choice(keypress_sounds[key])
    else:
        sound = random.choice(keypress_fallback)
    keypress_sounds_channel.play(sound)

# --- Stage runner ---
def run_stages():
    current_stage_id = stage_order[0]

    while current_stage_id:
        if not keyboard_connected():
            raise RuntimeError("KeyboardDisconnected")

        stage = stages_by_id[current_stage_id]
        play_blocking_stage_sound(stage["prompt"])  # during prompt, only keypress sounds

        fail_counters = {k: 0 for k in stage["fail"]}
        default_fail_counter = 0
        fail_count = 0
        next_stage_id = None
        correct_def = stage["correct"]

        # --- Case: normal stage ---
        while True:
            key = wait_for_key()

            correct_keys = correct_def
            if isinstance(correct_keys, str): correct_keys = [correct_keys]
            correct_keys = [ck.lower() for ck in correct_keys]

            if key in correct_keys:
                play(beep, block=False)
                play_blocking_stage_sound(stage["success"])
                print("Correct!")
                next_stage_id = stage.get("next_on_success")
                break
            else:
                fail_count += 1
                if key in stage["fail"]:
                    play(buzzer)
                    sounds = stage["fail"][key]
                    idx = fail_counters[key]
                    play_blocking_stage_sound(sounds[idx])
                    if idx < len(sounds)-1: fail_counters[key]+=1
                    print(f"Wrong key '{key}', try again...")
                elif stage["fail_default"]:
                    play(buzzer)
                    sounds = stage["fail_default"]
                    idx = default_fail_counter
                    play_blocking_stage_sound(sounds[idx])
                    if idx < len(sounds)-1: default_fail_counter+=1
                    print(f"Unexpected key '{key}', fallback fail triggered.")
                else:
                    play(buzzer)
                    print(f"Unexpected key '{key}', no fail sounds defined.")

                fb = stage.get("fail_branches", {})
                if str(fail_count) in fb:
                    branch_def = fb[str(fail_count)]
                    print("Special branch triggered. Waiting for input...")
                    branch_key = wait_for_key()
                    if branch_key in branch_def["keys"]:
                        next_stage_id = branch_def["keys"][branch_key]
                        break
                    else:
                        print(f"No branch for '{branch_key}', continuing fails...")

                if stage.get("next_on_fail"):
                    next_stage_id = stage["next_on_fail"]
                    break

        if not next_stage_id:
            idx = stage_order.index(stage["id"])
            if idx+1 < len(stage_order):
                next_stage_id = stage_order[idx+1]
            else:
                next_stage_id = None

        current_stage_id = next_stage_id

# --- Main controller ---
if __name__ == "__main__":
    wait_for_keyboard()
    sfx_channel.play(keyboard_connected_sound)
    music_channel.play(bg_music, loops=-1, fade_ms=2000)
    time.sleep(1)

    # start background listener thread
    threading.Thread(target=key_listener, daemon=True).start()

    run_stages()
    print("Game finished!")

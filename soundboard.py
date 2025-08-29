import pygame, random, json, time, atexit, os, sys
from evdev import InputDevice, list_devices, categorize, ecodes

# --- Init mixer (tuned for Pi 1B) ---
pygame.mixer.pre_init(22050, -16, 1, 256)
pygame.init()
pygame.mixer.init()

# --- Utility functions ---
def play(sound_or_list, block=True):
    """Play one sound (or random from a list). Blocks unless block=False."""
    sound = random.choice(sound_or_list) if isinstance(sound_or_list, list) else sound_or_list
    ch = sound.play()
    if block and ch is not None:
        while ch.get_busy():
            pygame.time.delay(10)

def load_sound_list(filenames):
    """Load .wav files into pygame Sound objects."""
    return [pygame.mixer.Sound(f) for f in filenames]

# --- Keyboard handling (grab ALL keyboards to prevent terminal input) ---
grabbed_devices = []

def grab_all_keyboards():
    """Find and grab ALL keyboard devices to prevent terminal input."""
    global grabbed_devices
    devices = [InputDevice(path) for path in list_devices()]
    main_keyboard = None
    
    for dev in devices:
        try:
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                name = dev.name.lower()
                print(f"Found input device: {dev.name} ({dev.path})")
                
                if "vc4-hdmi" in name or "gpio" in name or "virtual" in name:
                    print(f"  -> Skipped (virtual/system device)")
                    continue
                
                print(f"  -> Attempting to grab...")
                
                # Add small delay before grabbing (helps with some systems)
                time.sleep(0.1)
                
                # Try to grab exclusive access
                dev.grab()
                grabbed_devices.append(dev)
                print(f"  -> Successfully grabbed: {dev.name}")
                
                # Use the first successfully grabbed device as our main input
                if main_keyboard is None:
                    main_keyboard = dev
                    print(f"  -> Using as main input device")
                
        except PermissionError as e:
            print(f"  -> Permission denied: {e}")
            print(f"     Try running as root: sudo python3 {sys.argv[0]}")
            continue
        except Exception as e:
            print(f"  -> Error with {dev.name}: {e}")
            continue
    
    return main_keyboard

def open_keyboard():
    """Wrapper to maintain compatibility with existing code."""
    return grab_all_keyboards()

def release_keyboard(dev):
    """Release all grabbed keyboards."""
    global grabbed_devices
    for device in grabbed_devices:
        try:
            device.ungrab()
        except Exception:
            pass
    grabbed_devices = []

def release_keyboard(dev):
    try:
        dev.ungrab()
    except Exception:
        pass

def get_key_event(dev):
    """Block until a key press event is read, return a lowercase key string."""
    try:
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                if key_event.keystate == key_event.key_down:
                    code = key_event.keycode
                    if isinstance(code, list):   # sometimes a list
                        code = code[0]
                    if code.startswith("KEY_"):
                        return code[4:].lower()
                    return code.lower()
    except OSError:
        # device disappeared
        raise RuntimeError("KeyboardDisconnected")

def wait_for_keyboard():
    """Block until a real keyboard is connected and return the device."""
    print("Waiting for keyboard...")
    kb = None
    while not kb:
        kb = open_keyboard()
        if not kb:
            time.sleep(1)
    print(f"Keyboard detected: {kb.name} ({kb.path})")
    return kb

# Check if running as root (may be required for grabbing)
if os.geteuid() != 0:
    print("WARNING: Not running as root. If keyboard grab fails, try:")
    print("  sudo python3 your_script.py")
    print("  or add your user to the 'input' group:")
    print("  sudo usermod -a -G input $USER")
    print()

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

# --- Load keypress sounds ---
with open("keypress.json", "r") as f:
    kp_data = json.load(f)

keypress_sounds = {
    k.lower(): load_sound_list(v)
    for k, v in kp_data.get("keypress_sounds", {}).items()
}
keypress_fallback = load_sound_list(kp_data.get("keypress_fallback", []))

keypress_sounds_channel = pygame.mixer.Channel(2)

def play_keypress_sound(key):
    """Play a random sound for this key on the keypress channel."""
    if key in keypress_sounds:
        sound = random.choice(keypress_sounds[key])
    else:
        sound = random.choice(keypress_fallback)
    keypress_sounds_channel.play(sound)

# --- Global sounds ---
beep = pygame.mixer.Sound("beep.wav")
buzzer = pygame.mixer.Sound("buzzer.wav")
bg_music = pygame.mixer.Sound("background.wav")
keyboard_connected_sound = pygame.mixer.Sound("keyboard_connected.wav")

music_channel = pygame.mixer.Channel(0)
sfx_channel = pygame.mixer.Channel(1)

# --- Stage runner ---
def run_stages(kb):
    print("DEBUG: Starting run_stages")
    current_stage_id = stage_order[0]
    print(f"DEBUG: First stage ID: {current_stage_id}")

    while current_stage_id:
        stage = stages_by_id[current_stage_id]
        print(f"DEBUG: Playing prompt for stage {current_stage_id}")
        play(stage["prompt"])
        print(f"DEBUG: Prompt finished, now waiting for keyboard input...")

        fail_counters = {k: 0 for k in stage["fail"]}
        default_fail_counter = 0
        fail_count = 0
        next_stage_id = None
        correct_def = stage["correct"]
        print(f"DEBUG: Correct answer is: {correct_def}")

        # --- Case: sequence of keys ---
        if isinstance(correct_def, list) and len(correct_def) > 0 and isinstance(correct_def[0], list):
            print("DEBUG: Sequence mode detected")
            sequence = [k.lower() for k in correct_def[0]]
            seq_index = 0
            while seq_index < len(sequence):
                print(f"DEBUG: Waiting for key {seq_index+1} of {len(sequence)} in sequence...")
                key = get_key_event(kb)
                print(f"DEBUG: Received key: '{key}'")
                play_keypress_sound(key)
                if key == sequence[seq_index]:
                    play(beep, block=False)
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
            print("DEBUG: Normal mode - waiting for single key")
            while True:
                print(f"DEBUG: About to call get_key_event()...")
                key = get_key_event(kb)
                print(f"DEBUG: Received key from get_key_event: '{key}'")
                play_keypress_sound(key)

                correct_keys = correct_def
                if isinstance(correct_keys, str):
                    correct_keys = [correct_keys]
                correct_keys = [ck.lower() for ck in correct_keys]

                if key in correct_keys:
                    play(beep, block=False)
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
                        branch_key = get_key_event(kb)
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
    kb = wait_for_keyboard()
    atexit.register(release_keyboard, kb)

    # Feedback + fade in music
    sfx_channel.play(keyboard_connected_sound)
    music_channel.play(bg_music, loops=-1, fade_ms=2000)
    time.sleep(2)

    try:
        run_stages(kb)
        print("Game finished!")
        break
    except RuntimeError as e:
        if str(e) == "KeyboardDisconnected":
            print("Keyboard disconnected! Restarting from stage 1...")
            music_channel.fadeout(2000)
            continue
        else:
            raise

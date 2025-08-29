import pygame, random, json, time, threading, queue
from evdev import InputDevice, list_devices, categorize, ecodes

# --- Mixer init ---
pygame.mixer.pre_init(22050, -16, 1, 256)
pygame.init()
pygame.mixer.init()

# --- Queue for game logic keys ---
key_queue = queue.Queue()

# --- Utility ---
def play(sound_or_list, block=True):
    """Play one sound (or random from list). Blocks if block=True."""
    sound = random.choice(sound_or_list) if isinstance(sound_or_list, list) else sound_or_list
    ch = sound.play()
    if block and ch:
        while ch.get_busy():
            pygame.time.delay(10)

def load_sound_list(filenames):
    return [pygame.mixer.Sound(f) for f in filenames]

# --- Keyboard handling ---
def find_keyboard():
    devices = [InputDevice(path) for path in list_devices()]
    for dev in devices:
        try:
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                name = dev.name.lower()
                if "vc4-hdmi" in name or "gpio" in name or "virtual" in name:
                    continue
                return dev
        except: 
            continue
    return None

def keyboard_listener(dev):
    """Thread: read keys, always play typing sounds, push into queue for game logic."""
    try:
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                e = categorize(event)
                if e.keystate == e.key_down:
                    code = e.keycode
                    if isinstance(code, list): code = code[0]
                    if code.startswith("KEY_"): code = code[4:]
                    key = code.lower()
                    # Always play typing sound
                    play_keypress_sound(key)
                    # Push into queue for game logic
                    key_queue.put(key)
    except OSError:
        raise RuntimeError("KeyboardDisconnected")

def wait_for_keyboard():
    """Block until a real keyboard is connected and return device."""
    print("Waiting for keyboard...")
    kb = None
    while not kb:
        kb = find_keyboard()
        if not kb:
            time.sleep(1)
    print(f"Keyboard detected: {kb.name} ({kb.path})")
    return kb

# --- Load keypress sounds ---
with open("keypress.json") as f:
    kp_data = json.load(f)

keypress_sounds = {k.lower(): load_sound_list(v) for k,v in kp_data.get("keypress_sounds",{}).items()}
keypress_fallback = load_sound_list(kp_data.get("keypress_fallback", []))
keypress_sounds_channel = pygame.mixer.Channel(2)

def play_keypress_sound(key):
    if key in keypress_sounds:
        sound = random.choice(keypress_sounds[key])
    else:
        sound = random.choice(keypress_fallback)
    keypress_sounds_channel.play(sound)

# --- Load stages ---
with open("stages.json") as f:
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

# --- Global sounds ---
beep = pygame.mixer.Sound("beep.wav")
buzzer = pygame.mixer.Sound("buzzer.wav")
bg_music = pygame.mixer.Sound("background.wav")
keyboard_connected_sound = pygame.mixer.Sound("keyboard_connected.wav")

music_channel = pygame.mixer.Channel(0)
sfx_channel = pygame.mixer.Channel(1)

# --- Stage runner ---
def run_stages():
    current_stage_id = stage_order[0]

    while current_stage_id:
        stage = stages_by_id[current_stage_id]

        # clear queue before prompt
        while not key_queue.empty():
            key_queue.get_nowait()

        play(stage["prompt"], block=True)

        fail_counters = {k: 0 for k in stage["fail"]}
        default_fail_counter = 0
        fail_count = 0
        next_stage_id = None
        correct_def = stage["correct"]

        # --- Case: sequence ---
        if isinstance(correct_def, list) and len(correct_def) > 0 and isinstance(correct_def[0], list):
            sequence = [k.lower() for k in correct_def[0]]
            seq_index = 0
            while seq_index < len(sequence):
                key = key_queue.get(block=True)  # wait for new key
                if key == sequence[seq_index]:
                    play(beep, block=False)
                    seq_index += 1
                else:
                    play(buzzer)
                    if stage["fail_default"]:
                        idx = default_fail_counter
                        sounds = stage["fail_default"]
                        play(sounds[idx])
                        if idx < len(sounds)-1: default_fail_counter += 1
                    print("Wrong key in sequence, restarting...")
                    seq_index = 0
            play(stage["success"], block=True)
            print("Sequence completed!")
            next_stage_id = stage.get("next_on_success")

        # --- Case: normal ---
        else:
            while True:
                key = key_queue.get(block=True)  # wait for next key
                correct_keys = correct_def
                if isinstance(correct_keys, str): correct_keys = [correct_keys]
                correct_keys = [ck.lower() for ck in correct_keys]

                if key in correct_keys:
                    play(beep, block=False)
                    play(stage["success"], block=True)
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
                        if idx < len(sounds)-1: fail_counters[key]+=1
                        print(f"Wrong key '{key}', try again...")
                    elif stage["fail_default"]:
                        play(buzzer)
                        sounds = stage["fail_default"]
                        idx = default_fail_counter
                        play(sounds[idx])
                        if idx < len(sounds)-1: default_fail_counter+=1
                        print(f"Unexpected key '{key}', fallback fail triggered.")
                    else:
                        play(buzzer)
                        print(f"Unexpected key '{key}', no fail sounds defined.")

                    # --- check fail_branches ---
                    fb = stage.get("fail_branches", {})
                    if str(fail_count) in fb:
                        branch_def = fb[str(fail_count)]
                        print("Special branch triggered. Waiting for input...")
                        branch_key = key_queue.get(block=True)
                        if branch_key in branch_def["keys"]:
                            next_stage_id = branch_def["keys"][branch_key]
                            break
                        else:
                            print(f"No branch for '{branch_key}', continuing fails...")

                    # --- optional direct fail jump ---
                    if stage.get("next_on_fail"):
                        next_stage_id = stage["next_on_fail"]
                        break

        # --- Move to next stage ---
        if not next_stage_id:
            idx = stage_order.index(stage["id"])
            if idx+1 < len(stage_order):
                next_stage_id = stage_order[idx+1]
            else:
                next_stage_id = None

        current_stage_id = next_stage_id

# --- Main controller ---
while True:
    kb = wait_for_keyboard()
    sfx_channel.play(keyboard_connected_sound)
    music_channel.play(bg_music, loops=-1, fade_ms=2000)
    time.sleep(1)

    # Start background thread
    listener_thread = threading.Thread(target=keyboard_listener, args=(kb,), daemon=True)
    listener_thread.start()

    try:
        run_stages()
        print("Game finished!")
        break
    except RuntimeError as e:
        if str(e) == "KeyboardDisconnected":
            print("Keyboard disconnected! Restarting...")
            music_channel.fadeout(2000)
            continue
        else:
            raise
